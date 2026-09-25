"""Test de fumée du retriever du prototype porté (index FAISS d'origine + mistral-embed)."""

import sys
from pathlib import Path

import pytest

PROTOTYPE_DIR = Path(__file__).resolve().parents[1] / "prototype"
sys.path.insert(
    0, str(PROTOTYPE_DIR)
)  # rend le package `utils` du prototype importable

from utils.config import MISTRAL_API_KEY
from utils.vector_store import VectorStoreManager

QUESTION = "Quel joueur a le meilleur pourcentage à 3 points ?"


def test_index_loads():
    vs = VectorStoreManager()
    assert vs.index is not None
    assert vs.index.ntotal == len(vs.document_chunks)


@pytest.mark.skipif(not MISTRAL_API_KEY, reason="MISTRAL_API_KEY absente")
def test_search_returns_k_results():
    vs = VectorStoreManager()
    results = vs.search(QUESTION, k=5)
    assert len(results) == 5


if __name__ == "__main__":
    vs = VectorStoreManager()
    for r in vs.search(QUESTION, k=5):
        print(round(r["score"], 1), r["metadata"]["source"])
