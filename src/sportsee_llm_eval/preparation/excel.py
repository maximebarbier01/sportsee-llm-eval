"""Lecture et nettoyage du classeur Excel NBA livré par SportSee.

Le fichier brut (data/raw/regular NBA.xlsx) est laissé intact : toutes les corrections sont
faites ici, pour être reproductibles sur un nouvel export (autre saison, autre club).

Défauts corrigés (relevés à l'audit) :
- « Données NBA » : une ligne de numéros de colonnes (1…53) au-dessus des vrais en-têtes,
  8 colonnes vides en fin de feuille, en-tête 3PM converti par Excel en heure 15:00:00 ;
- « Dictionnaire des données » : même en-tête 3PM corrompu et décrit comme « minutes jouées
  après 15:00 », statistiques décrites « par match » alors que ce sont des totaux de saison,
  clé « + / - » qui ne correspond pas à la colonne « +/- » ;
- « Analyse » et « Analyse Vide » : tableaux croisés dynamiques dont les valeurs ne sont pas
  stockées dans les cellules (vides à la lecture) et agrégats recalculables : ignorées.

Incohérences signalées sans être corrigées (impossible de savoir quelle valeur est juste) :
REB ≠ OREB + DREB et PTS ≠ 2×FGM + 3PM + FTM sur une partie des joueurs (écarts de quelques
unités, probablement du bruit dans le jeu de données).

Usage :
    python -m sportsee_llm_eval.preparation.excel
"""

import argparse
import datetime as dt
import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_EXCEL = PROJECT_ROOT / "data" / "raw" / "regular NBA.xlsx"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

SHEET_PLAYERS = "Données NBA"
SHEET_TEAMS = "Equipe"
SHEET_DICTIONARY = "Dictionnaire des données"

PLAYER_COLUMNS = [
    "Player", "Team", "Age", "GP", "W", "L", "Min", "PTS", "FGM", "FGA", "FG%", "3PM", "3PA",
    "3P%", "FTM", "FTA", "FT%", "OREB", "DREB", "REB", "AST", "TOV", "STL", "BLK", "PF", "FP",
    "DD2", "TD3", "+/-", "OFFRTG", "DEFRTG", "NETRTG", "AST%", "AST/TO", "AST RATIO", "OREB%",
    "DREB%", "REB%", "TO RATIO", "EFG%", "TS%", "USG%", "PACE", "PIE", "POSS",
]  # fmt: skip

# Clés du dictionnaire mal saisies -> nom réel de la colonne dans « Données NBA »
DICTIONARY_KEY_FIXES = {"+ / -": "+/-"}

# Descriptions fausses ou ambiguës. Les statistiques de comptage sont des totaux de saison
# (ex. Shai Gilgeous-Alexander : 2485 PTS en 76 matchs) ; seules Min et +/- sont des moyennes.
DESCRIPTION_FIXES = {
    "PTS": "Points marqués (total sur la saison)",
    "FGM": "Tirs réussis (Field Goals Made, total sur la saison)",
    "FGA": "Tirs tentés (Field Goals Attempted, total sur la saison)",
    "3PM": "Tirs à 3 points réussis (3-Pointers Made, total sur la saison)",
    "3PA": "Tirs à 3 points tentés (3-Pointers Attempted, total sur la saison)",
    "FTM": "Lancers francs réussis (Free Throws Made, total sur la saison)",
    "FTA": "Lancers francs tentés (Free Throws Attempted, total sur la saison)",
    "OREB": "Rebonds offensifs (total sur la saison)",
    "DREB": "Rebonds défensifs (total sur la saison)",
    "REB": "Rebonds (offensifs + défensifs, total sur la saison)",
    "AST": "Passes décisives (Assists, total sur la saison)",
    "TOV": "Balles perdues (Turnovers, total sur la saison)",
    "STL": "Interceptions (Steals, total sur la saison)",
    "BLK": "Contres (Blocks, total sur la saison)",
    "PF": "Fautes personnelles (total sur la saison)",
    "FP": "Fantasy Points (total sur la saison)",
    "DD2": "Nombre de double-doubles (≥ 10 dans deux catégories principales)",
    "TD3": "Nombre de triple-doubles (≥ 10 dans trois catégories principales)",
    "+/-": "Plus-Minus moyen par match (écart de score lorsque le joueur est sur le terrain)",
}


def _fix_header(label: object) -> object:
    """Excel a converti l'en-tête « 3PM » en heure (15:00:00) : on le rétablit."""
    return "3PM" if isinstance(label, dt.time) else label


def read_players(path: Path = RAW_EXCEL) -> pd.DataFrame:
    """Statistiques de saison par joueur (une ligne par joueur)."""
    # ligne 0 = numéros de colonnes (1…53), ligne 1 = vrais en-têtes
    df = pd.read_excel(path, sheet_name=SHEET_PLAYERS, header=1)
    df = df.dropna(axis=1, how="all")  # colonnes vides en fin de feuille
    df = df.rename(columns=_fix_header)
    if list(df.columns) != PLAYER_COLUMNS:
        raise ValueError(
            f"Colonnes inattendues dans « {SHEET_PLAYERS} » : {list(df.columns)}"
        )
    if df["Player"].duplicated().any():
        doublons = df.loc[df["Player"].duplicated(), "Player"].tolist()
        raise ValueError(f"Joueurs en double : {doublons}")
    return df.reset_index(drop=True)


def read_teams(path: Path = RAW_EXCEL) -> pd.DataFrame:
    """Correspondance code équipe -> nom complet."""
    df = pd.read_excel(path, sheet_name=SHEET_TEAMS)
    df.columns = ["code", "nom"]
    return df


def read_dictionary(path: Path = RAW_EXCEL) -> pd.DataFrame:
    """Dictionnaire des colonnes de « Données NBA », corrigé."""
    # ligne 0 = titre de la feuille
    df = pd.read_excel(path, sheet_name=SHEET_DICTIONARY, header=None, skiprows=1)
    df.columns = ["colonne", "description"]
    df["colonne"] = df["colonne"].map(_fix_header).replace(DICTIONARY_KEY_FIXES)
    fixes = df["colonne"].map(DESCRIPTION_FIXES)
    df["description"] = fixes.fillna(df["description"])
    manquantes = set(PLAYER_COLUMNS) - set(df["colonne"])
    inconnues = set(df["colonne"]) - set(PLAYER_COLUMNS)
    if manquantes or inconnues:
        raise ValueError(
            f"Dictionnaire incohérent : non décrites {sorted(manquantes)}, "
            f"inconnues {sorted(inconnues)}"
        )
    return df


def quality_report(players: pd.DataFrame, teams: pd.DataFrame) -> dict:
    """Incohérences internes signalées (non corrigées)."""
    reb_gap = players["REB"] - (players["OREB"] + players["DREB"])
    pts_gap = players["PTS"] - (2 * players["FGM"] + players["3PM"] + players["FTM"])
    unknown_teams = sorted(set(players["Team"]) - set(teams["code"]))
    return {
        "joueurs": len(players),
        "equipes": players["Team"].nunique(),
        "equipes_inconnues": unknown_teams,
        "reb_different_oreb_plus_dreb": {
            "joueurs": int((reb_gap != 0).sum()),
            "ecart_max": int(reb_gap.abs().max()),
        },
        "pts_different_2fgm_plus_3pm_plus_ftm": {
            "joueurs": int((pts_gap != 0).sum()),
            "ecart_max": int(pts_gap.abs().max()),
        },
    }


def prepare_excel(raw_path: Path = RAW_EXCEL, out_dir: Path = PROCESSED_DIR) -> dict:
    """Lit le classeur brut, le nettoie et écrit les tables propres en CSV."""
    players = read_players(raw_path)
    teams = read_teams(raw_path)
    dictionary = read_dictionary(raw_path)
    report = quality_report(players, teams)

    out_dir.mkdir(parents=True, exist_ok=True)
    players.to_csv(out_dir / "joueurs.csv", index=False)
    teams.to_csv(out_dir / "equipes.csv", index=False)
    dictionary.to_csv(out_dir / "dictionnaire.csv", index=False)
    (out_dir / "qualite_excel.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    for key in ("reb_different_oreb_plus_dreb", "pts_different_2fgm_plus_3pm_plus_ftm"):
        if report[key]["joueurs"]:
            logger.warning("Incohérence %s : %s", key, report[key])
    logger.info(
        "%s joueurs, %s équipes, %s colonnes décrites -> %s",
        len(players),
        len(teams),
        len(dictionary),
        out_dir,
    )
    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="Nettoyage du classeur Excel NBA")
    parser.add_argument("--raw", type=Path, default=RAW_EXCEL)
    parser.add_argument("--out", type=Path, default=PROCESSED_DIR)
    args = parser.parse_args()
    prepare_excel(args.raw, args.out)


if __name__ == "__main__":
    main()
