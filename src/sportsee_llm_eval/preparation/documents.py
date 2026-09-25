"""Documents indexés issus de l'Excel : une fiche par joueur, une par équipe, une par colonne.

Le prototype découpait la feuille « Données NBA » en blocs de 1 500 caractères de tableau
(df.to_string) : sans en-têtes après le premier bloc, ces fragments n'étaient jamais
retrouvés par la recherche (0 sur 160 extraits récupérés lors de la baseline).

Ici, chaque joueur devient une fiche rédigée où chaque valeur est accompagnée de son
intitulé : la recherche peut rapprocher « 3P% de Curry » de la fiche de Curry. Chaque ligne
est validée par PlayerSeasonStats avant d'être rédigée.
"""

import pandas as pd
from pydantic import ValidationError

from sportsee_llm_eval.preparation.excel import RAW_EXCEL, SHEET_PLAYERS
from sportsee_llm_eval.preparation.schemas import (
    DictionaryEntry,
    IndexedDocument,
    PlayerSeasonStats,
    Team,
)

EXCEL_SOURCE = RAW_EXCEL.name


def _n(value: float, decimals: int = 1) -> str:
    """Nombre au format français : 37.5 -> « 37,5 »."""
    return f"{value:.{decimals}f}".replace(".", ",")


def validate_players(df: pd.DataFrame) -> list[PlayerSeasonStats]:
    """Valide chaque ligne ; lève une erreur listant toutes les lignes invalides."""
    players, errors = [], []
    for i, row in enumerate(df.to_dict(orient="records")):
        try:
            players.append(PlayerSeasonStats.model_validate(row))
        except ValidationError as e:
            errors.append(f"ligne {i + 2} ({row.get('Player')}) : {e}")
    if errors:
        raise ValueError(f"{len(errors)} ligne(s) invalide(s) :\n" + "\n".join(errors))
    return players


def validate_teams(df: pd.DataFrame) -> list[Team]:
    return [Team.model_validate(row) for row in df.to_dict(orient="records")]


def validate_dictionary(df: pd.DataFrame) -> list[DictionaryEntry]:
    return [DictionaryEntry.model_validate(row) for row in df.to_dict(orient="records")]


def player_document(p: PlayerSeasonStats, team_name: str) -> IndexedDocument:
    per_game = (lambda total: _n(total / p.gp)) if p.gp else (lambda total: "—")
    text = (
        f"Fiche joueur : {p.player} ({team_name}, code {p.team}), {p.age} ans.\n"
        f"Saison régulière : {p.gp} matchs joués ({p.w} victoires, {p.l} défaites), "
        f"{_n(p.min)} minutes par match.\n"
        f"Points : {p.pts} au total sur la saison (soit {per_game(p.pts)} par match). "
        f"Tirs : {p.fgm} réussis sur {p.fga} tentés ({_n(p.fg_pct)} %). "
        f"Tirs à 3 points : {p.fg3m} réussis sur {p.fg3a} tentés ({_n(p.fg3_pct)} %). "
        f"Lancers francs : {p.ftm} réussis sur {p.fta} tentés ({_n(p.ft_pct)} %).\n"
        f"Rebonds : {p.reb} au total (soit {per_game(p.reb)} par match ; "
        f"{p.oreb} offensifs, {p.dreb} défensifs). "
        f"Passes décisives : {p.ast} (soit {per_game(p.ast)} par match). "
        f"Balles perdues : {p.tov}. Interceptions : {p.stl}. Contres : {p.blk}. "
        f"Fautes personnelles : {p.pf}.\n"
        f"Double-doubles : {p.dd2}. Triple-doubles : {p.td3}. "
        f"Plus-minus moyen par match : {_n(p.plus_minus)}. Fantasy points : {p.fp}.\n"
        f"Statistiques avancées : Offensive Rating {_n(p.off_rtg)}, Defensive Rating "
        f"{_n(p.def_rtg)}, Net Rating {_n(p.net_rtg)}, True Shooting % {_n(p.ts_pct)}, "
        f"Effective FG % {_n(p.efg_pct)}, Usage % {_n(p.usg_pct)}, Assist % "
        f"{_n(p.ast_pct)}, ratio passes/pertes {_n(p.ast_to, 2)}, Rebound % "
        f"{_n(p.reb_pct)}, PIE (Player Impact Estimate) {_n(p.pie)}, "
        f"Pace {_n(p.pace, 2)}, {p.poss} possessions jouées."
    )
    return IndexedDocument(
        doc_id=f"joueur::{p.player}",
        source_type="joueur",
        source=f"{EXCEL_SOURCE} ({SHEET_PLAYERS})",
        text=text,
        player=p.player,
        team=p.team,
    )


def team_document(team: Team, roster: list[PlayerSeasonStats]) -> IndexedDocument:
    """Fiche équipe : effectif trié par points, pour les questions sur une équipe."""
    roster = sorted(roster, key=lambda p: p.pts, reverse=True)
    lines = "\n".join(
        f"- {p.player} : {p.pts} points, {p.reb} rebonds, {p.ast} passes décisives "
        f"({p.gp} matchs)"
        for p in roster
    )
    text = (
        f"Fiche équipe : {team.nom} (code {team.code}). "
        f"{len(roster)} joueurs dans les données de la saison régulière.\n"
        f"Effectif, du meilleur au moins bon marqueur (totaux sur la saison) :\n{lines}"
    )
    return IndexedDocument(
        doc_id=f"equipe::{team.code}",
        source_type="equipe",
        source=f"{EXCEL_SOURCE} ({SHEET_PLAYERS} + Equipe)",
        text=text,
        team=team.code,
    )


def dictionary_document(entry: DictionaryEntry) -> IndexedDocument:
    return IndexedDocument(
        doc_id=f"dictionnaire::{entry.colonne}",
        source_type="dictionnaire",
        source=f"{EXCEL_SOURCE} (Dictionnaire des données)",
        text=f"Définition de la statistique « {entry.colonne} » : {entry.description}.",
    )


def build_excel_documents(
    players_df: pd.DataFrame, teams_df: pd.DataFrame, dictionary_df: pd.DataFrame
) -> list[IndexedDocument]:
    players = validate_players(players_df)
    teams = validate_teams(teams_df)
    dictionary = validate_dictionary(dictionary_df)
    names = {t.code: t.nom for t in teams}
    unknown = {p.team for p in players} - names.keys()
    if unknown:
        raise ValueError(
            f"Codes équipe absents de la feuille Equipe : {sorted(unknown)}"
        )

    documents = [player_document(p, names[p.team]) for p in players]
    documents += [
        team_document(t, [p for p in players if p.team == t.code]) for t in teams
    ]
    documents += [dictionary_document(e) for e in dictionary]
    return documents
