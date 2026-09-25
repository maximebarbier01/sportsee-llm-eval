"""Schémas Pydantic des entrées/sorties de l'évaluation.

Valident le jeu de questions gelé avant tout appel payant à l'API, et fixent le format
des réponses sauvegardées (answers.jsonl) pour pouvoir relancer la notation seule.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Categorie = Literal[
    "simple", "complexe", "bruitee", "texte", "mixte", "hors_couverture"
]


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[SCBTMH]\d{2}$")
    categorie: Categorie
    question: str = Field(min_length=1)
    ground_truth: str = Field(min_length=1)
    source: str
    calcul: str


class QuestionSet(BaseModel):
    version: str
    statut: str
    sources: dict[str, str]
    notes: list[str]
    questions: list[Question] = Field(min_length=1)

    @model_validator(mode="after")
    def ids_uniques(self) -> "QuestionSet":
        ids = [q.id for q in self.questions]
        doublons = {i for i in ids if ids.count(i) > 1}
        if doublons:
            raise ValueError(
                f"Identifiants de questions en double : {sorted(doublons)}"
            )
        return self


class RagOutput(BaseModel):
    """Ce qu'un système RAG évalué doit renvoyer pour une question."""

    answer: str
    contexts: list[str]
    retrieval_empty: bool = False


class RagAnswer(RagOutput):
    """Une ligne de answers.jsonl : la question, la référence et la sortie du système."""

    id: str
    categorie: Categorie
    question: str
    ground_truth: str
    latency_s: float
