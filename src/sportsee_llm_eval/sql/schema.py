"""Schéma relationnel SQLite de SportSee (SQLAlchemy).

Tables :
- teams            : les 30 équipes (code à 3 lettres, nom complet) ;
- players          : un joueur par ligne, rattaché à son équipe ;
- stats            : statistiques de saison régulière d'un joueur (relation 1-1 avec players) ;
- reports          : les rapports textuels (threads Reddit r/nba) ;
- report_messages  : les messages d'un rapport (post initial et commentaires).

Pas de table `matches` : les données fournies ne contiennent que des totaux de saison, sans
résultat ni statistique par match (écart à la consigne confirmé avec le mentor). Les
questions « par match » ou « domicile / extérieur » sont donc hors du périmètre des données.

Les colonnes de `stats` portent des noms SQL simples (fg3_pct plutôt que « 3P% ») : moins de
guillemets à générer pour le LLM, moins d'erreurs. La correspondance avec les en-têtes de
l'Excel est dans COLUMN_LABELS.
"""

import unicodedata
from pathlib import Path

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = PROJECT_ROOT / "data" / "database" / "sportsee.db"


class Base(DeclarativeBase):
    pass


class TeamRow(Base):
    __tablename__ = "teams"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    players: Mapped[list["PlayerRow"]] = relationship(back_populates="team")


class PlayerRow(Base):
    __tablename__ = "players"

    player_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # nom en minuscules sans accents (« nikola jokic ») : recherche tolérante aux accents
    search_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    team_code: Mapped[str] = mapped_column(
        ForeignKey("teams.code"), nullable=False, index=True
    )
    age: Mapped[int] = mapped_column(Integer, CheckConstraint("age BETWEEN 15 AND 50"))

    team: Mapped[TeamRow] = relationship(back_populates="players")
    stats: Mapped["StatsRow"] = relationship(back_populates="player")


class StatsRow(Base):
    """Totaux de saison régulière (sauf minutes_per_game et plus_minus : moyennes par match)."""

    __tablename__ = "stats"
    __table_args__ = (
        CheckConstraint("w + l = gp", name="victoires_plus_defaites"),
        CheckConstraint(
            "fg3m <= fg3a AND fgm <= fga AND ftm <= fta", name="reussis_tentes"
        ),
    )

    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.player_id"), primary_key=True
    )
    gp: Mapped[int] = mapped_column(Integer, nullable=False)
    w: Mapped[int] = mapped_column(Integer, nullable=False)
    l: Mapped[int] = mapped_column(Integer, nullable=False)
    minutes_per_game: Mapped[float] = mapped_column(Float)
    pts: Mapped[int] = mapped_column(Integer)
    fgm: Mapped[int] = mapped_column(Integer)
    fga: Mapped[int] = mapped_column(Integer)
    fg_pct: Mapped[float] = mapped_column(Float)
    fg3m: Mapped[int] = mapped_column(Integer)
    fg3a: Mapped[int] = mapped_column(Integer)
    fg3_pct: Mapped[float] = mapped_column(Float)
    ftm: Mapped[int] = mapped_column(Integer)
    fta: Mapped[int] = mapped_column(Integer)
    ft_pct: Mapped[float] = mapped_column(Float)
    oreb: Mapped[int] = mapped_column(Integer)
    dreb: Mapped[int] = mapped_column(Integer)
    reb: Mapped[int] = mapped_column(Integer)
    ast: Mapped[int] = mapped_column(Integer)
    tov: Mapped[int] = mapped_column(Integer)
    stl: Mapped[int] = mapped_column(Integer)
    blk: Mapped[int] = mapped_column(Integer)
    pf: Mapped[int] = mapped_column(Integer)
    fp: Mapped[int] = mapped_column(Integer)
    dd2: Mapped[int] = mapped_column(Integer)
    td3: Mapped[int] = mapped_column(Integer)
    plus_minus: Mapped[float] = mapped_column(Float)
    off_rtg: Mapped[float] = mapped_column(Float)
    def_rtg: Mapped[float] = mapped_column(Float)
    net_rtg: Mapped[float] = mapped_column(Float)
    ast_pct: Mapped[float] = mapped_column(Float)
    ast_to: Mapped[float] = mapped_column(Float)
    ast_ratio: Mapped[float] = mapped_column(Float)
    oreb_pct: Mapped[float] = mapped_column(Float)
    dreb_pct: Mapped[float] = mapped_column(Float)
    reb_pct: Mapped[float] = mapped_column(Float)
    to_ratio: Mapped[float] = mapped_column(Float)
    efg_pct: Mapped[float] = mapped_column(Float)
    ts_pct: Mapped[float] = mapped_column(Float)
    usg_pct: Mapped[float] = mapped_column(Float)
    pace: Mapped[float] = mapped_column(Float)
    pie: Mapped[float] = mapped_column(Float)
    poss: Mapped[int] = mapped_column(Integer)

    player: Mapped[PlayerRow] = relationship(back_populates="stats")


class ReportRow(Base):
    __tablename__ = "reports"

    report_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_file: Mapped[str] = mapped_column(String, nullable=False)

    messages: Mapped[list["ReportMessageRow"]] = relationship(back_populates="report")


class ReportMessageRow(Base):
    __tablename__ = "report_messages"

    message_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.report_id"), index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    author: Mapped[str | None] = mapped_column(String)
    is_post: Mapped[bool] = mapped_column(Boolean, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    report: Mapped[ReportRow] = relationship(back_populates="messages")


# Colonne de `stats` -> en-tête de l'Excel (et du dictionnaire des données)
COLUMN_LABELS = {
    "gp": "GP", "w": "W", "l": "L", "minutes_per_game": "Min", "pts": "PTS", "fgm": "FGM",
    "fga": "FGA", "fg_pct": "FG%", "fg3m": "3PM", "fg3a": "3PA", "fg3_pct": "3P%",
    "ftm": "FTM", "fta": "FTA", "ft_pct": "FT%", "oreb": "OREB", "dreb": "DREB", "reb": "REB",
    "ast": "AST", "tov": "TOV", "stl": "STL", "blk": "BLK", "pf": "PF", "fp": "FP",
    "dd2": "DD2", "td3": "TD3", "plus_minus": "+/-", "off_rtg": "OFFRTG", "def_rtg": "DEFRTG",
    "net_rtg": "NETRTG", "ast_pct": "AST%", "ast_to": "AST/TO", "ast_ratio": "AST RATIO",
    "oreb_pct": "OREB%", "dreb_pct": "DREB%", "reb_pct": "REB%", "to_ratio": "TO RATIO",
    "efg_pct": "EFG%", "ts_pct": "TS%", "usg_pct": "USG%", "pace": "PACE", "pie": "PIE",
    "poss": "POSS",
}  # fmt: skip


def search_name(name: str) -> str:
    """« Nikola Jokić » -> « nikola jokic » (minuscules, sans accents)."""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _enable_foreign_keys(dbapi_connection, _record) -> None:
    dbapi_connection.execute("PRAGMA foreign_keys = ON")


def get_engine(db_path: Path = DB_PATH, read_only: bool = False) -> Engine:
    """Moteur SQLite. En lecture seule, toute écriture est refusée par SQLite lui-même."""
    if read_only:
        url = f"sqlite:///file:{db_path}?mode=ro&uri=true"
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    event.listen(engine, "connect", _enable_foreign_keys)
    return engine
