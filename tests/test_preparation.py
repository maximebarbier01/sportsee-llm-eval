"""Tests du pipeline de préparation : schémas Pydantic, fiches joueur, parseur Reddit."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sportsee_llm_eval.preparation.documents import (
    build_excel_documents,
    player_document,
    validate_players,
)
from sportsee_llm_eval.preparation.excel import (
    RAW_EXCEL,
    read_dictionary,
    read_players,
    read_teams,
)
from sportsee_llm_eval.preparation.reddit import (
    _strip_vote_suffix,
    parse_thread,
    thread_documents,
)
from sportsee_llm_eval.preparation.schemas import PlayerSeasonStats

needs_excel = pytest.mark.skipif(not RAW_EXCEL.exists(), reason="classeur brut absent")

VALID_ROW = {
    "Player": "Test Player", "Team": "OKC", "Age": 25, "GP": 10, "W": 6, "L": 4,
    "Min": 30.0, "PTS": 200, "FGM": 80, "FGA": 160, "FG%": 50.0, "3PM": 20, "3PA": 50,
    "3P%": 40.0, "FTM": 20, "FTA": 25, "FT%": 80.0, "OREB": 10, "DREB": 40, "REB": 50,
    "AST": 30, "TOV": 15, "STL": 8, "BLK": 3, "PF": 20, "FP": 400, "DD2": 1, "TD3": 0,
    "+/-": -1.5, "OFFRTG": 110.0, "DEFRTG": 112.0, "NETRTG": -2.0, "AST%": 15.0,
    "AST/TO": 2.0, "AST RATIO": 18.0, "OREB%": 4.0, "DREB%": 15.0, "REB%": 9.0,
    "TO RATIO": 10.0, "EFG%": 56.0, "TS%": 58.0, "USG%": 22.0, "PACE": 100.0,
    "PIE": 10.0, "POSS": 700,
}  # fmt: skip


# --------------------------------------------------------------------------- schémas


def test_ligne_valide():
    p = PlayerSeasonStats.model_validate(VALID_ROW)
    assert (p.player, p.fg3m, p.plus_minus) == ("Test Player", 20, -1.5)


@pytest.mark.parametrize(
    "change, message",
    [
        ({"3PM": 60}, "3PM > 3PA"),
        ({"W": 7}, r"W \+ L"),
        ({"FG%": 120.0}, "less than or equal to 100"),
        ({"Team": "okc"}, "pattern"),
        ({"Colonne inconnue": 1}, "Extra inputs"),
    ],
)
def test_ligne_invalide(change, message):
    with pytest.raises(ValidationError, match=message):
        PlayerSeasonStats.model_validate({**VALID_ROW, **change})


@needs_excel
def test_toutes_les_lignes_du_classeur_sont_valides():
    assert len(validate_players(read_players())) == 569


@needs_excel
def test_fiche_joueur_porte_valeurs_et_intitules():
    curry = next(
        p for p in validate_players(read_players()) if p.player == "Stephen Curry"
    )
    doc = player_document(curry, "Golden State Warriors")
    assert "Tirs à 3 points : 308 réussis sur 784 tentés (39,7 %)" in doc.text
    assert (doc.player, doc.team, doc.source_type) == ("Stephen Curry", "GSW", "joueur")


@needs_excel
def test_documents_excel():
    docs = build_excel_documents(read_players(), read_teams(), read_dictionary())
    types = [d.source_type for d in docs]
    assert (
        types.count("joueur"),
        types.count("equipe"),
        types.count("dictionnaire"),
    ) == (
        569,
        30,
        45,
    )
    bos = next(d for d in docs if d.doc_id == "equipe::BOS")
    assert "Jayson Tatum : 1930 points" in bos.text


# --------------------------------------------------------------------------- Reddit

PAGE_1 = """12/06/2025 13:06

Best shooters this year ? : r/nba

Accéder au contenu principal

Se connecter

r/nba • il y a 1 m.

OriginalPoster

### Best shooters this year ?

Curry is still the best shooter in the league.

31

Partager

shoesbrand • Sponsorisé(e)

Buy our shoes now!

### Rejoindre la conversation

Trier par : Meilleurs

alice_fan • -1 m.

Comm. du top 1%

Klay was great too but he is declining.

186

Répondre

https://www.reddit.com/r/nba/comments/abc/best_shooters/

1/2"""

PAGE_2 = """12/06/2025 13:06

Best shooters this year ? : r/nba

Se connecter

#### bob-42 AO • -3 j

Totally agree with that take on Curry. 3 → □ Répondre ...

2 réponses supplémentaires

r/nba • il y a 2 m.

Another unrelated thread about trades

55 upvotes · 150 commentaires

https://www.reddit.com/r/nba/comments/abc/best_shooters/

2/2"""


def test_parse_thread_retire_le_decor():
    messages = parse_thread([PAGE_1, PAGE_2], "t1")
    assert [(m.author, m.is_post) for m in messages] == [
        ("OriginalPoster", True),
        ("alice_fan", False),
        ("bob-42", False),  # ligne d'auteur précédée de « #### »
    ]
    texts = [m.text for m in messages]
    assert texts[0] == "Curry is still the best shooter in the league."
    assert texts[2] == "Totally agree with that take on Curry."
    joined = " ".join(texts)
    for noise in [
        "shoes",
        "Répondre",
        "Se connecter",
        "Comm. du top",
        "unrelated",
        "□",
    ]:
        assert noise not in joined  # publicité, boutons, badges, publications connexes
    assert messages[0].thread_title == "Best shooters this year ?"


@pytest.mark.parametrize(
    "line, expected",
    [
        ("they did jokic. 3 → □ Répondre ...", "they did jokic."),
        ("Edit: fixed it. ♀ 9 ♦ ☐ Répondre ...", "Edit: fixed it."),
        ("Thank you! -2 ↓", "Thank you!"),
        (
            "his rTS was 115.",
            "his rTS was 115.",
        ),  # un vrai nombre en fin de phrase est gardé
        ("he scored 30 points", "he scored 30 points"),
    ],
)
def test_strip_vote_suffix(line, expected):
    assert _strip_vote_suffix(line) == expected


def test_thread_documents_decoupe_proprement():
    messages = parse_thread([PAGE_1, PAGE_2], "t1")
    long_post = messages[0].model_copy(update={"text": "Word sentence here. " * 200})
    docs = thread_documents([long_post, *messages[1:]], source="Reddit test.pdf")
    posts = [d for d in docs if d.is_thread_post]
    assert len(posts) > 1  # post long découpé en plusieurs documents
    for d in docs:
        assert d.text.startswith(
            "Discussion Reddit r/nba « Best shooters this year ? »"
        )
        assert len(d.text) <= 1500
    body = posts[0].text.split("\n", 1)[1]
    assert body.endswith(("here.", "here"))  # jamais coupé au milieu d'un mot
