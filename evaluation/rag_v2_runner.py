"""Adaptateur d'évaluation du système rag_v2 (pipeline de préparation + Pydantic AI)."""

import sys
from pathlib import Path

from schemas import RagOutput

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sportsee_llm_eval.rag.rag_v2 import RagV2


class RagV2Runner:
    name = "rag_v2"

    def __init__(self) -> None:
        self.rag = RagV2()

    def config(self) -> dict:
        return {
            "system": self.name,
            "model": self.rag.model_name,
            "temperature": 0.0,
            "k": self.rag.k,
            "index_vectors": self.rag.store.index.ntotal,
            "extras": "post initial des threads Reddit joint au contexte ; sortie structurée Pydantic AI",
        }

    def answer(self, question: str) -> RagOutput:
        response, documents = self.rag.ask(question)
        return RagOutput(
            answer=response.reponse,
            contexts=[d.page_content for d in documents],
            retrieval_empty=not documents,
        )
