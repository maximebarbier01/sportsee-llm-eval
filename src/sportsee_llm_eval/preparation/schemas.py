"""Schémas Pydantic du pipeline de préparation : données d'entrée et documents indexés.

Chaque ligne de données passe par ces modèles avant d'être indexée (et, à l'étape 2,
insérée en base) : une ligne invalide est rejetée avec un message explicite au lieu de
polluer silencieusement l'index.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Pct = Field(ge=0, le=100)


class PlayerSeasonStats(BaseModel):
    """Une ligne de « Données NBA » : statistiques de saison régulière d'un joueur.

    Les statistiques de comptage (PTS, REB, AST...) sont des totaux de saison ; Min et +/-
    sont des moyennes par match. Les alias sont les noms de colonnes de l'Excel.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True, frozen=True)

    player: str = Field(alias="Player", min_length=1)
    team: str = Field(alias="Team", pattern=r"^[A-Z]{3}$")
    age: int = Field(alias="Age", ge=15, le=50)
    gp: int = Field(alias="GP", ge=0, le=82)
    w: int = Field(alias="W", ge=0)
    l: int = Field(alias="L", ge=0)
    min: float = Field(alias="Min", ge=0, le=48)
    pts: int = Field(alias="PTS", ge=0)
    fgm: int = Field(alias="FGM", ge=0)
    fga: int = Field(alias="FGA", ge=0)
    fg_pct: float = Field(alias="FG%", ge=0, le=100)
    fg3m: int = Field(alias="3PM", ge=0)
    fg3a: int = Field(alias="3PA", ge=0)
    fg3_pct: float = Field(alias="3P%", ge=0, le=100)
    ftm: int = Field(alias="FTM", ge=0)
    fta: int = Field(alias="FTA", ge=0)
    ft_pct: float = Field(alias="FT%", ge=0, le=100)
    oreb: int = Field(alias="OREB", ge=0)
    dreb: int = Field(alias="DREB", ge=0)
    reb: int = Field(alias="REB", ge=0)
    ast: int = Field(alias="AST", ge=0)
    tov: int = Field(alias="TOV", ge=0)
    stl: int = Field(alias="STL", ge=0)
    blk: int = Field(alias="BLK", ge=0)
    pf: int = Field(alias="PF", ge=0)
    fp: int = Field(alias="FP", ge=0)
    dd2: int = Field(alias="DD2", ge=0)
    td3: int = Field(alias="TD3", ge=0)
    plus_minus: float = Field(alias="+/-")
    off_rtg: float = Field(alias="OFFRTG", ge=0)
    def_rtg: float = Field(alias="DEFRTG", ge=0)
    net_rtg: float = Field(alias="NETRTG")
    ast_pct: float = Field(alias="AST%", ge=0, le=100)
    ast_to: float = Field(alias="AST/TO", ge=0)
    ast_ratio: float = Field(alias="AST RATIO", ge=0, le=100)
    oreb_pct: float = Field(alias="OREB%", ge=0, le=100)
    dreb_pct: float = Field(alias="DREB%", ge=0, le=100)
    reb_pct: float = Field(alias="REB%", ge=0, le=100)
    to_ratio: float = Field(alias="TO RATIO", ge=0, le=100)
    # EFG% et TS% dépassent 100 sur de très petits volumes (ex. 1 tir à 3 points réussi)
    efg_pct: float = Field(alias="EFG%", ge=0, le=150)
    ts_pct: float = Field(alias="TS%", ge=0, le=150)
    usg_pct: float = Field(alias="USG%", ge=0, le=100)
    pace: float = Field(alias="PACE", ge=0)
    pie: float = Field(alias="PIE")
    poss: int = Field(alias="POSS", ge=0)

    @model_validator(mode="after")
    def coherence(self) -> "PlayerSeasonStats":
        errors = []
        if self.w + self.l != self.gp:
            errors.append(f"W + L ({self.w} + {self.l}) != GP ({self.gp})")
        for made, att, name in [
            (self.fgm, self.fga, "FGM > FGA"),
            (self.fg3m, self.fg3a, "3PM > 3PA"),
            (self.ftm, self.fta, "FTM > FTA"),
            (self.fg3m, self.fgm, "3PM > FGM"),
        ]:
            if made > att:
                errors.append(name)
        if errors:
            raise ValueError(f"{self.player} : {', '.join(errors)}")
        return self


class Team(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str = Field(pattern=r"^[A-Z]{3}$")
    nom: str = Field(min_length=1)


class DictionaryEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    colonne: str = Field(min_length=1)
    description: str = Field(min_length=1)


class RedditComment(BaseModel):
    """Un message d'un thread Reddit (post initial ou commentaire), après nettoyage OCR."""

    model_config = ConfigDict(frozen=True)

    thread_id: str
    thread_title: str
    author: str | None = None
    text: str = Field(min_length=1)
    is_post: bool = False


SourceType = Literal["joueur", "equipe", "dictionnaire", "reddit"]


class IndexedDocument(BaseModel):
    """Un document prêt à être vectorisé, avec les métadonnées utilisées au filtrage."""

    model_config = ConfigDict(frozen=True)

    doc_id: str = Field(min_length=1)
    source_type: SourceType
    source: str = Field(
        min_length=1, description="Fichier et feuille / thread d'origine"
    )
    text: str = Field(min_length=20, max_length=4000)
    player: str | None = None
    team: str | None = None
    thread_title: str | None = None
    is_thread_post: bool | None = None  # extrait du post initial d'un thread Reddit
