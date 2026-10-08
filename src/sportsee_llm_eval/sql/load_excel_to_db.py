"""Pipeline d'ingestion : Excel (et rapports Reddit) -> validation Pydantic -> base SQLite.

Étapes :
    1. lecture du classeur avec les corrections de excel.py (en-tête décalé, 3PM, colonnes vides) ;
    2. validation de chaque ligne par les modèles Pydantic de l'étape 1 (PlayerSeasonStats,
       Team) : une ligne invalide arrête l'ingestion avec la liste de toutes les erreurs ;
    3. messages Reddit issus du parseur de l'étape 1 (OCR Mistral en cache) ;
    4. recréation de la base et insertion dans une seule transaction, puis contrôle des volumes.

La base est recréée à chaque exécution : elle est entièrement dérivée des fichiers sources.

Usage :
    python -m sportsee_llm_eval.sql.load_excel_to_db
"""

import argparse
import logging
from pathlib import Path

import logfire
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sportsee_llm_eval.observability.logfire_setup import setup_logfire
from sportsee_llm_eval.preparation.documents import validate_players, validate_teams
from sportsee_llm_eval.preparation.excel import RAW_EXCEL, read_players, read_teams
from sportsee_llm_eval.preparation.ocr import load_or_ocr, reddit_pdfs
from sportsee_llm_eval.preparation.reddit import parse_thread
from sportsee_llm_eval.preparation.schemas import PlayerSeasonStats, RedditComment
from sportsee_llm_eval.sql.schema import (
    DB_PATH,
    Base,
    PlayerRow,
    ReportMessageRow,
    ReportRow,
    StatsRow,
    TeamRow,
    get_engine,
    search_name,
)

logger = logging.getLogger(__name__)

# champs de PlayerSeasonStats rangés ailleurs que dans `stats`, ou renommés
_NOT_IN_STATS = {"player", "team", "age"}
_RENAMED = {"min": "minutes_per_game"}


def stats_row(player_id: int, p: PlayerSeasonStats) -> StatsRow:
    values = p.model_dump(exclude=_NOT_IN_STATS)
    return StatsRow(
        player_id=player_id, **{_RENAMED.get(k, k): v for k, v in values.items()}
    )


def load_reports() -> list[tuple[ReportRow, list[RedditComment]]]:
    reports = []
    for pdf in reddit_pdfs():
        report_id = pdf.stem.lower().replace(" ", "_")
        messages = parse_thread(load_or_ocr(pdf), report_id)
        report = ReportRow(
            report_id=report_id, title=messages[0].thread_title, source_file=pdf.name
        )
        reports.append((report, messages))
    return reports


def load_excel_to_db(raw_excel: Path = RAW_EXCEL, db_path: Path = DB_PATH) -> dict:
    with logfire.span("lecture et validation Pydantic") as span:
        players = validate_players(read_players(raw_excel))
        teams = validate_teams(read_teams(raw_excel))
        unknown = {p.team for p in players} - {t.code for t in teams}
        if unknown:
            raise ValueError(f"Codes équipe inconnus : {sorted(unknown)}")
        reports = load_reports()
        span.set_attribute("joueurs", len(players))

    engine = get_engine(db_path)
    with logfire.span("insertion SQLite", base=str(db_path)):
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        with Session(engine) as session, session.begin():  # une seule transaction
            session.add_all(TeamRow(code=t.code, name=t.nom) for t in teams)
            for player_id, p in enumerate(players, start=1):
                session.add(
                    PlayerRow(
                        player_id=player_id,
                        name=p.player,
                        search_name=search_name(p.player),
                        team_code=p.team,
                        age=p.age,
                    )
                )
                session.add(stats_row(player_id, p))
            for report, messages in reports:
                session.add(report)
                session.add_all(
                    ReportMessageRow(
                        report_id=report.report_id,
                        position=i,
                        author=m.author,
                        is_post=m.is_post,
                        text=m.text,
                    )
                    for i, m in enumerate(messages)
                )

    with Session(engine) as session:
        counts = {
            table.__tablename__: session.scalar(select(func.count()).select_from(table))
            for table in (TeamRow, PlayerRow, StatsRow, ReportRow, ReportMessageRow)
        }
    expected = {"teams": len(teams), "players": len(players), "stats": len(players)}
    for table, n in expected.items():
        if counts[table] != n:
            raise RuntimeError(
                f"{table} : {counts[table]} lignes insérées, {n} attendues"
            )
    logfire.info("base SQLite chargée", **counts)
    logger.info("Base %s : %s", db_path, counts)
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="Ingestion Excel -> SQLite")
    parser.add_argument("--raw", type=Path, default=RAW_EXCEL)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()
    setup_logfire(service_name="sportsee-pipeline")
    with logfire.span("ingestion Excel -> SQLite"):
        load_excel_to_db(args.raw, args.db)
    logfire.force_flush()


if __name__ == "__main__":
    main()
