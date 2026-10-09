"""Tests de l'étape 2 : schéma, ingestion, contrôle des requêtes et exemples few-shot."""

import json
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from sportsee_llm_eval.preparation.excel import RAW_EXCEL
from sportsee_llm_eval.preparation.ocr import OCR_CACHE_DIR
from sportsee_llm_eval.sql.load_excel_to_db import load_excel_to_db
from sportsee_llm_eval.sql.schema import (
    COLUMN_LABELS,
    StatsRow,
    get_engine,
    search_name,
)
from sportsee_llm_eval.sql.sql_tool import (
    FEW_SHOT_EXAMPLES,
    check_player_aggregate,
    check_sql,
    clean_sql,
    enforce_ranking_limit,
)

QUESTIONS_FILE = (
    Path(__file__).resolve().parents[1]
    / "evaluation"
    / "questions"
    / "questions_v1.json"
)
needs_data = pytest.mark.skipif(
    not RAW_EXCEL.exists() or not any(OCR_CACHE_DIR.glob("*.json")),
    reason="classeur brut ou cache OCR absent",
)


# --------------------------------------------------------------------------- contrôle SQL


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT name FROM players",
        "select p.name from players p where p.age < 23",
        "WITH t AS (SELECT * FROM stats) SELECT COUNT(*) FROM t",
    ],
)
def test_requetes_de_lecture_acceptees(sql):
    check_sql(sql)


@pytest.mark.parametrize(
    "sql, message",
    [
        ("DELETE FROM players", "SELECT"),
        ("SELECT 1; DROP TABLE players", "une seule instruction"),
        ("SELECT 1; SELECT 2", "une seule instruction"),
        ("WITH x AS (DELETE FROM players) SELECT 1", "DELETE"),
        ("PRAGMA table_info(players)", "SELECT"),
        ("", "vide"),
    ],
)
def test_requetes_dangereuses_refusees(sql, message):
    with pytest.raises(ValueError, match=message):
        check_sql(sql)


def test_clean_sql():
    assert clean_sql("```sql\nSELECT 1;\n```") == "SELECT 1"
    assert clean_sql("  SELECT name FROM players ;  ") == "SELECT name FROM players"


def test_search_name():
    assert search_name("Nikola Jokić") == "nikola jokic"
    assert search_name("Jonas Valančiūnas") == "jonas valanciunas"


def test_toutes_les_colonnes_stats_ont_un_libelle_excel():
    columns = {c.name for c in StatsRow.__table__.columns} - {"player_id"}
    assert columns == set(COLUMN_LABELS)


def test_few_shot_sans_fuite_du_jeu_d_evaluation():
    """Les exemples few-shot enseignent des formes de requête, pas les réponses du test."""
    questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))["questions"]
    eval_questions = {q["question"].lower().strip() for q in questions}
    for example in FEW_SHOT_EXAMPLES:
        assert example["question"].lower().strip() not in eval_questions
        check_sql(clean_sql(example["sql"]))


# --------------------------------------------------------------------------- ingestion


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "sportsee_test.db"
    load_excel_to_db(db_path=path)
    return path


@needs_data
def test_ingestion_volumes_et_valeurs(db_path):
    engine = get_engine(db_path, read_only=True)
    with engine.connect() as conn:
        count = lambda table: conn.execute(
            text(f"SELECT COUNT(*) FROM {table}")
        ).scalar()
        assert [count(t) for t in ("teams", "players", "stats", "reports")] == [
            30,
            569,
            569,
            4,
        ]
        assert count("report_messages") > 300
        top = conn.execute(
            text(
                "SELECT p.name, s.pts FROM stats s JOIN players p USING (player_id) "
                "ORDER BY s.pts DESC LIMIT 1"
            )
        ).one()
        assert tuple(top) == ("Shai Gilgeous-Alexander", 2485)
        jokic = conn.execute(
            text("SELECT name FROM players WHERE search_name LIKE '%jokic%'")
        ).scalar()
        assert jokic == "Nikola Jokić"


@needs_data
def test_base_en_lecture_seule(db_path):
    engine = get_engine(db_path, read_only=True)
    with engine.connect() as conn, pytest.raises(OperationalError, match="readonly"):
        conn.execute(text("DELETE FROM teams"))


@needs_data
def test_contraintes_appliquees_par_sqlite(db_path):
    engine = get_engine(db_path)
    with (
        engine.connect() as conn,
        pytest.raises(Exception, match="(?i)foreign key|constraint"),
    ):
        conn.execute(
            text(
                "INSERT INTO players (player_id, name, search_name, team_code, age) "
                "VALUES (9999, 'X', 'x', 'ZZZ', 20)"
            )
        )
        conn.commit()


@needs_data
def test_exemples_few_shot_s_executent(db_path):
    engine = get_engine(db_path, read_only=True)
    with engine.connect() as conn:
        for example in FEW_SHOT_EXAMPLES:
            rows = conn.execute(text(clean_sql(example["sql"]))).fetchall()
            assert rows, example["question"]


# --------------------------------------------------------------------------- garde-fous


@pytest.mark.parametrize(
    "sql",
    [
        (
            "SELECT p.name, SUM(s.pts) FROM stats s JOIN players p ON p.player_id = s.player_id "
            "WHERE p.search_name LIKE '%curry%'"
        ),
        (
            "SELECT AVG(s.reb) FROM stats s JOIN players p USING (player_id) "
            "WHERE p.name IN ('A', 'B')"
        ),
    ],
)
def test_agregat_sur_nom_refuse(sql):
    with pytest.raises(ValueError, match="une ligne par joueur"):
        check_player_aggregate(sql)


@pytest.mark.parametrize(
    "sql",
    [
        (
            "SELECT t.name, SUM(s.pts) FROM stats s JOIN players p USING (player_id) "
            "JOIN teams t ON t.code = p.team_code WHERE t.name LIKE '%Jazz%' GROUP BY t.name"
        ),
        (
            "SELECT ROUND(AVG(p.age), 1) FROM players p JOIN teams t ON t.code = p.team_code "
            "WHERE t.name LIKE '%Lakers%'"
        ),
        (
            "SELECT p.name, s.pts FROM stats s JOIN players p USING (player_id) "
            "WHERE p.search_name LIKE '%curry%'"
        ),
    ],
)
def test_agregats_legitimes_acceptes(sql):
    check_player_aggregate(sql)


def test_limit_1_reecrit_sur_un_classement():
    assert enforce_ranking_limit("SELECT a FROM t ORDER BY a DESC LIMIT 1").endswith(
        "LIMIT 5"
    )
    assert enforce_ranking_limit("SELECT a FROM t LIMIT 1").endswith(
        "LIMIT 1"
    )  # pas de tri
    assert enforce_ranking_limit("SELECT a FROM t ORDER BY a LIMIT 10").endswith(
        "LIMIT 10"
    )


def test_exemples_few_shot_respectent_les_garde_fous():
    for example in FEW_SHOT_EXAMPLES:
        check_player_aggregate(clean_sql(example["sql"]))
