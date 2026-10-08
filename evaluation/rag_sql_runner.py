"""Adaptateur d'évaluation du système rag_sql (agent Pydantic AI + recherche + outil SQL)."""

import sys
from pathlib import Path

from schemas import RagOutput

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sportsee_llm_eval.rag.rag_sql import RagSql


class RagSqlRunner:
    name = "rag_sql"

    def __init__(self) -> None:
        self.agent = RagSql()

    def config(self) -> dict:
        return {
            "system": self.name,
            "model": self.agent.model_name,
            "temperature": 0.0,
            "k": self.agent.rag.k,
            "index_vectors": self.agent.rag.store.index.ntotal,
            "extras": "agent Pydantic AI avec outils rechercher_documents et "
            "interroger_base_statistiques (LangChain SQL, few-shot, lecture seule)",
        }

    def answer(self, question: str) -> RagOutput:
        response, deps = self.agent.ask(question)
        # contexte RAGAS = résultats d'outils réellement vus par le modèle (documents + SQL)
        return RagOutput(
            answer=response.reponse,
            contexts=deps.contexts,
            retrieval_empty=not deps.contexts,
        )
