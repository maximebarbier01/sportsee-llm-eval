"""Outil LangChain SQL : question en langage naturel -> requête SQL -> résultats.

1. Génération : mistral-small reçoit le schéma de la base (DDL + exemples de lignes, via
   LangChain SQLDatabase), un glossaire des colonnes et des exemples few-shot couvrant les
   formes de requête courantes (classement, filtre avec seuil, agrégation par équipe,
   comparaison de joueurs, moyenne par match, nom approché).
2. Contrôle : une seule instruction, SELECT / WITH uniquement, aucun mot-clé d'écriture.
3. Exécution sur une connexion SQLite en lecture seule (défense en profondeur : même une
   requête d'écriture qui passerait le contrôle serait refusée par SQLite).
4. En cas d'erreur SQL, une nouvelle génération avec le message d'erreur (auto-correction).

Les exemples few-shot ne reprennent aucune question du jeu d'évaluation : ils enseignent des
formes de requête, pas des réponses.
"""

import json
import re
from pathlib import Path

import logfire
from dotenv import load_dotenv
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import ChatPromptTemplate, FewShotChatMessagePromptTemplate
from langchain_core.tools import BaseTool, tool
from langchain_mistralai import ChatMistralAI
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from sportsee_llm_eval.observability.logfire_setup import setup_logfire
from sportsee_llm_eval.sql.schema import (
    COLUMN_LABELS,
    DB_PATH,
    PROJECT_ROOT,
    get_engine,
)

MODEL_NAME = "mistral-small-latest"
MAX_ROWS = 25

FEW_SHOT_EXAMPLES = [
    {
        "question": "Quels sont les 5 meilleurs passeurs de la saison ?",
        "sql": "SELECT p.name, p.team_code, s.ast FROM stats s "
        "JOIN players p ON p.player_id = s.player_id ORDER BY s.ast DESC LIMIT 5;",
    },
    {
        "question": "Meilleur pourcentage aux lancers francs parmi les joueurs ayant tenté "
        "au moins 200 lancers francs ?",
        "sql": "SELECT p.name, p.team_code, s.ft_pct, s.ftm, s.fta FROM stats s "
        "JOIN players p ON p.player_id = s.player_id WHERE s.fta >= 200 "
        "ORDER BY s.ft_pct DESC LIMIT 5;",
    },
    {
        "question": "Combien de contres les joueurs du Utah Jazz ont-ils réalisés au total ?",
        "sql": "SELECT t.name, SUM(s.blk) AS total_contres FROM stats s "
        "JOIN players p ON p.player_id = s.player_id JOIN teams t ON t.code = p.team_code "
        "WHERE t.name LIKE '%Jazz%' GROUP BY t.name;",
    },
    {
        "question": "Quelles équipes ont pris le plus de rebonds offensifs au total ?",
        "sql": "SELECT t.code, t.name, SUM(s.oreb) AS total_oreb FROM stats s "
        "JOIN players p ON p.player_id = s.player_id JOIN teams t ON t.code = p.team_code "
        "GROUP BY t.code ORDER BY total_oreb DESC LIMIT 5;",
    },
    {
        "question": "Compare les points par match de Devin Booker et Kevin Durant.",
        "sql": "SELECT p.name, s.pts, s.gp, ROUND(1.0 * s.pts / s.gp, 1) AS pts_par_match "
        "FROM stats s JOIN players p ON p.player_id = s.player_id "
        "WHERE p.name IN ('Devin Booker', 'Kevin Durant');",
    },
    {
        "question": "combien de passes pour luka doncic",
        "sql": "SELECT p.name, p.team_code, s.ast FROM stats s "
        "JOIN players p ON p.player_id = s.player_id "
        "WHERE p.search_name LIKE '%doncic%';",
    },
    {
        "question": "Quel est l'âge moyen des joueurs du Miami Heat, et le plus âgé ?",
        "sql": "SELECT ROUND(AVG(p.age), 1) AS age_moyen, MAX(p.age) AS age_max, "
        "COUNT(*) AS joueurs FROM players p JOIN teams t ON t.code = p.team_code "
        "WHERE t.name LIKE '%Heat%';",
    },
    {
        "question": "Combien de joueurs ont réalisé au moins 20 double-doubles, et lesquels ?",
        "sql": "SELECT COUNT(*) OVER () AS nombre_joueurs, p.name, s.dd2 FROM stats s "
        "JOIN players p ON p.player_id = s.player_id WHERE s.dd2 >= 20 "
        "ORDER BY s.dd2 DESC;",
    },
    {
        "question": "Parmi les joueurs de moins de 23 ans ayant joué au moins 50 matchs, "
        "lesquels ont le meilleur True Shooting % ?",
        "sql": "SELECT p.name, p.age, s.gp, s.ts_pct FROM stats s "
        "JOIN players p ON p.player_id = s.player_id WHERE p.age < 23 AND s.gp >= 50 "
        "ORDER BY s.ts_pct DESC LIMIT 5;",
    },
]

INSTRUCTIONS = """\
Tu écris une requête SQLite qui répond à la question, à partir du schéma ci-dessous.

{schema}

Glossaire des colonnes de la table stats :
{glossary}

Règles :
- Réponds UNIQUEMENT par la requête SQL, sans explication ni bloc de code.
- Une seule instruction SELECT (ou WITH ... SELECT), jamais d'écriture.
- Les statistiques de comptage sont des totaux de saison ; pour une moyenne par match, \
divise par s.gp (1.0 * s.pts / s.gp). minutes_per_game et plus_minus sont déjà des moyennes.
- Pour chercher un joueur, filtre sur players.search_name (nom en minuscules, sans \
accents) avec LIKE et le nom de famille écrit en minuscules sans accents : \
p.search_name LIKE '%jokic%'. Si l'orthographe semble fautive, garde la partie sûre du nom. \
Une équipe peut être désignée par son nom complet, sa ville, son surnom ou son code à \
3 lettres : filtre sur teams.name avec LIKE ou sur le code.
- Pour un classement, renvoie quelques lignes (LIMIT 5) pour montrer les suivants.
- Ajoute les colonnes utiles à la réponse (nom, équipe, valeur, volume de tentatives).
- Les données ne contiennent que des totaux de saison régulière : aucune donnée par match, \
par date ou domicile / extérieur. Si la question en dépend, réponds exactement : \
SELECT 'donnees_indisponibles' AS erreur;
"""

FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|DETACH|PRAGMA|VACUUM|REINDEX)\b",
    re.IGNORECASE,
)


class SqlResult(BaseModel):
    """Résultat structuré d'un appel à l'outil SQL."""

    question: str
    sql: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list] = Field(default_factory=list)
    truncated: bool = False
    error: str | None = None

    def to_text(self) -> str:
        if self.error:
            return f"Requête : {self.sql}\nErreur : {self.error}"
        lines = [f"Requête : {self.sql}", f"Colonnes : {', '.join(self.columns)}"]
        lines += [json.dumps(row, ensure_ascii=False) for row in self.rows]
        if not self.rows:
            lines.append("Aucune ligne.")
        if self.truncated:
            lines.append(f"(résultat tronqué à {MAX_ROWS} lignes)")
        return "\n".join(lines)


def clean_sql(raw: str) -> str:
    """Retire un éventuel bloc de code markdown et le point-virgule final."""
    sql = re.sub(r"^```(?:sql)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
    return sql.strip().rstrip(";").strip()


def check_sql(sql: str) -> None:
    """Lève ValueError si la requête n'est pas une lecture simple."""
    if not sql:
        raise ValueError("requête vide")
    if ";" in sql:
        raise ValueError("une seule instruction SQL est autorisée")
    if not re.match(r"^(SELECT|WITH)\b", sql, re.IGNORECASE):
        raise ValueError("seules les requêtes SELECT sont autorisées")
    match = FORBIDDEN.search(sql)
    if match:
        raise ValueError(f"mot-clé interdit : {match[0].upper()}")


def build_glossary() -> str:
    """Glossaire colonne SQL -> en-tête Excel -> description corrigée du dictionnaire."""
    from sportsee_llm_eval.preparation.excel import RAW_EXCEL, read_dictionary

    descriptions = {}
    if RAW_EXCEL.exists():
        descriptions = dict(read_dictionary().itertuples(index=False, name=None))
    return "\n".join(
        f"- {col} ({label}) : {descriptions.get(label, '')}".rstrip(" :")
        for col, label in COLUMN_LABELS.items()
    )


class SqlTool:
    def __init__(self, db_path: Path = DB_PATH, model_name: str = MODEL_NAME) -> None:
        load_dotenv(PROJECT_ROOT / ".env")
        setup_logfire()
        if not db_path.exists():
            raise FileNotFoundError(
                f"Base absente : {db_path}. Lancer « python -m "
                "sportsee_llm_eval.sql.load_excel_to_db »."
            )
        self.engine = get_engine(db_path, read_only=True)
        self.db = SQLDatabase(self.engine, sample_rows_in_table_info=2)
        self.model_name = model_name
        example_prompt = ChatPromptTemplate.from_messages(
            [("human", "{question}"), ("ai", "{sql}")]
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", INSTRUCTIONS),
                FewShotChatMessagePromptTemplate(
                    examples=FEW_SHOT_EXAMPLES, example_prompt=example_prompt
                ),
                ("human", "{question}"),
            ]
        ).partial(schema=self.db.get_table_info(), glossary=build_glossary())
        llm = ChatMistralAI(model=model_name, temperature=0, max_retries=5)
        self.chain = prompt | llm

    def generate(self, question: str, previous_error: str | None = None) -> str:
        if previous_error:
            question = (
                f"{question}\n\n(La requête précédente a échoué : {previous_error}. "
                "Corrige-la.)"
            )
        return clean_sql(self.chain.invoke({"question": question}).content)

    def execute(self, sql: str) -> tuple[list[str], list[list], bool]:
        with self.engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [list(r) for r in result.fetchmany(MAX_ROWS + 1)]
        return columns, rows[:MAX_ROWS], len(rows) > MAX_ROWS

    def run(self, question: str) -> SqlResult:
        error = None
        sql = ""
        with logfire.span("outil SQL", question=question) as span:
            for attempt in (1, 2):  # une auto-correction au plus
                sql = self.generate(question, previous_error=error)
                try:
                    check_sql(sql)
                    columns, rows, truncated = self.execute(sql)
                except (
                    ValueError,
                    SQLAlchemyError,
                ) as e:  # requête refusée / erreur SQLite
                    error = str(e).split("\n")[0]
                    logfire.warn(
                        "requête SQL en échec", sql=sql, erreur=error, essai=attempt
                    )
                    continue
                span.set_attributes(
                    {"sql": sql, "lignes": len(rows), "essais": attempt}
                )
                return SqlResult(
                    question=question,
                    sql=sql,
                    columns=columns,
                    rows=rows,
                    truncated=truncated,
                )
            span.set_attributes({"sql": sql, "erreur": error})
            return SqlResult(question=question, sql=sql, error=error)

    def as_langchain_tool(self) -> BaseTool:
        @tool("interroger_base_statistiques")
        def interroger_base_statistiques(question: str) -> str:
            """Répond à une question chiffrée sur les statistiques de saison des joueurs et
            des équipes NBA (classements, filtres, totaux, moyennes, comparaisons) en
            générant et exécutant une requête SQL sur la base SportSee."""
            return self.run(question).to_text()

        return interroger_base_statistiques
