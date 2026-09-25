"""Tests du nettoyage du classeur Excel NBA (nécessitent data/raw/regular NBA.xlsx)."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sportsee_llm_eval.preparation.excel import (
    PLAYER_COLUMNS,
    RAW_EXCEL,
    SHEET_PLAYERS,
    prepare_excel,
    read_dictionary,
    read_players,
    read_teams,
)

pytestmark = pytest.mark.skipif(
    not RAW_EXCEL.exists(), reason="classeur brut absent (données non versionnées)"
)

# Fichier nettoyé à la main par Maxime : sert de vérité terrain tant qu'il existe
REFERENCE_EXCEL = RAW_EXCEL.parents[1] / "reference" / "regular NBA clean.xlsx"


@pytest.fixture(scope="module")
def players():
    return read_players()


def test_joueurs_colonnes_et_taille(players):
    assert list(players.columns) == PLAYER_COLUMNS
    assert players.shape == (569, 45)
    assert players["Player"].is_unique


def test_joueurs_valeurs_connues(players):
    sga = players.set_index("Player").loc["Shai Gilgeous-Alexander"]
    assert (sga["Team"], sga["PTS"], sga["GP"], sga["3PM"]) == ("OKC", 2485, 76, 160)


def test_dictionnaire_corrige():
    d = read_dictionary().set_index("colonne")["description"]
    assert set(d.index) == set(PLAYER_COLUMNS)
    assert "3 points réussis" in d["3PM"]
    assert "15:00" not in " ".join(d)
    for col in ["PTS", "FGM", "FGA", "3PA"]:
        assert "total sur la saison" in d[col]
    assert "moyennes jouées par match" in d["Min"]  # Min reste une moyenne


def test_equipes():
    teams = read_teams()
    assert len(teams) == 30
    assert teams.set_index("code").loc["MIN", "nom"] == "Minnesota Timberwolves"


def test_prepare_excel_ecrit_les_tables(tmp_path):
    report = prepare_excel(out_dir=tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {
        "joueurs.csv",
        "equipes.csv",
        "dictionnaire.csv",
        "qualite_excel.json",
    }
    assert report["equipes_inconnues"] == []
    relu = pd.read_csv(tmp_path / "joueurs.csv")
    assert relu.shape == (569, 45)


@pytest.mark.skipif(not REFERENCE_EXCEL.exists(), reason="fichier de référence absent")
def test_identique_au_nettoyage_manuel(players):
    ref = pd.read_excel(REFERENCE_EXCEL, sheet_name=SHEET_PLAYERS).dropna(
        axis=1, how="all"
    )
    assert list(ref.columns) == list(players.columns)
    pd.testing.assert_frame_equal(players, ref, check_dtype=False)
    ref_teams = pd.read_excel(REFERENCE_EXCEL, sheet_name="Equipe")
    assert ref_teams.values.tolist() == read_teams().values.tolist()
    ref_dict = pd.read_excel(
        REFERENCE_EXCEL, sheet_name="Dictionnaire des données", header=None, skiprows=1
    )
    # mêmes colonnes décrites, à la clé « + / - » près, que le code normalise en « +/- »
    assert set(ref_dict[0].replace({"+ / -": "+/-"})) == set(
        read_dictionary()["colonne"]
    )
