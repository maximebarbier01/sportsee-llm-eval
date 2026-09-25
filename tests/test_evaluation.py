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
