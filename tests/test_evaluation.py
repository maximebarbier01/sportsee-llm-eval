"""Tests hors-ligne du banc d'évaluation : fidélité de l'adaptateur au prototype et schémas."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

EVAL_DIR = Path(__file__).resolve().parents[1] / "evaluation"
sys.path.insert(0, str(EVAL_DIR))

from prototype_runner import (
    MISTRAL_CHAT_FILE,
    NO_CONTEXT_MESSAGE,
    format_context,
    load_prototype_prompt,
    load_prototype_temperature,
)
from schemas import QuestionSet

QUESTIONS_FILE = EVAL_DIR / "questions" / "questions_v1.json"


def test_prompt_extrait_du_prototype():
    prompt = load_prototype_prompt()
    assert prompt.startswith("Tu es 'NBA Analyst AI'")
    assert "{context_str}" in prompt and "{question}" in prompt
    # le template doit se formater comme dans MistralChat.py (SYSTEM_PROMPT.format(...))
    rendu = prompt.format(context_str="CTX", question="Q?")
    assert "CTX" in rendu and "Q?" in rendu


def test_temperature_extraite_du_prototype():
    assert load_prototype_temperature() == 0.1


def test_format_context_identique_au_prototype():
    source = MISTRAL_CHAT_FILE.read_text(encoding="utf-8")
    # garde-fou : si le formatage du prototype change, ce test casse
    assert (
        "f\"Source: {res['metadata'].get('source', 'Inconnue')} (Score: {res['score']:.1f}%)\\nContenu: {res['text']}\""
        in source
    )
    assert NO_CONTEXT_MESSAGE in source

    results = [
        {"score": 80.24, "text": "A", "metadata": {"source": "x.pdf"}},
        {"score": 79.5, "text": "B", "metadata": {}},
    ]
    assert (
        format_context(results)
        == "Source: x.pdf (Score: 80.2%)\nContenu: A\n\n---\n\nSource: Inconnue (Score: 79.5%)\nContenu: B"
    )
    assert format_context([]) == NO_CONTEXT_MESSAGE


def test_jeu_de_questions_valide():
    qs = QuestionSet.model_validate_json(QUESTIONS_FILE.read_text(encoding="utf-8"))
    assert len(qs.questions) == 32
    assert {q.categorie for q in qs.questions} == {
        "simple",
        "complexe",
        "bruitee",
        "texte",
        "mixte",
        "hors_couverture",
    }


def test_schema_rejette_categorie_inconnue_et_doublons():
    base = {"version": "t", "statut": "t", "sources": {}, "notes": []}
    q = {
        "id": "S01",
        "categorie": "simple",
        "question": "q",
        "ground_truth": "r",
        "source": "s",
        "calcul": "c",
    }
    with pytest.raises(ValidationError):
        QuestionSet.model_validate(
            {**base, "questions": [{**q, "categorie": "facile"}]}
        )
    with pytest.raises(ValidationError, match="double"):
        QuestionSet.model_validate({**base, "questions": [q, q]})


ROBUSTESSE_FILE = EVAL_DIR / "questions" / "robustesse_v1.json"


def test_jeu_de_robustesse_valide():
    qs = QuestionSet.model_validate_json(ROBUSTESSE_FILE.read_text(encoding="utf-8"))
    assert len(qs.questions) == 26
    for q in qs.questions:
        refus_attendu = q.categorie in {"hors_couverture", "injection"}
        # une question à laquelle les données répondent indique les outils nécessaires
        assert bool(q.outils_attendus) != refus_attendu, q.id


def test_jeux_sans_question_commune():
    v1 = QuestionSet.model_validate_json(QUESTIONS_FILE.read_text(encoding="utf-8"))
    rob = QuestionSet.model_validate_json(ROBUSTESSE_FILE.read_text(encoding="utf-8"))
    assert not {q.question for q in v1.questions} & {q.question for q in rob.questions}
    assert not {q.id for q in v1.questions} & {q.id for q in rob.questions}


def test_choix_d_outils(tmp_path):
    import pandas as pd
    from evaluate_ragas import add_tool_choice

    scores = pd.DataFrame(
        {
            "id": ["R05", "R09", "R21"],
            "outils_appeles": [
                "interroger_base_statistiques,rechercher_documents",
                "interroger_base_statistiques",  # R09 attend la recherche documentaire
                "",
            ],
        }
    )
    result = add_tool_choice(scores, ROBUSTESSE_FILE)
    assert result["outils_conformes"].tolist()[:2] == [1.0, 0.0]
    assert pd.isna(
        result["outils_conformes"].iloc[2]
    )  # injection : aucun outil attendu
