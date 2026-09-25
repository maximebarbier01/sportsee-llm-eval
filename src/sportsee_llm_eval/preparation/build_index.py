"""Construction de l'index vectoriel rag_v2 : nettoyage -> documents validés -> embeddings.

Étapes :
    1. Excel : lecture corrigée (excel.py), fiches joueur / équipe / dictionnaire (documents.py)
    2. Reddit : OCR Mistral en cache (ocr.py), nettoyage et découpage en messages (reddit.py)
    3. Validation Pydantic de chaque document (IndexedDocument), identifiants uniques
    4. Embeddings mistral-embed et index LangChain FAISS avec métadonnées

Les feuilles « Analyse » et « Analyse Vide » ne sont plus indexées (agrégats recalculables,
tableaux croisés sans valeurs). Les documents sont aussi écrits en JSONL pour inspection.

Usage :
    python -m sportsee_llm_eval.preparation.build_index
"""

import argparse
import collections
import json
import logging
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_mistralai import MistralAIEmbeddings

from sportsee_llm_eval.preparation.documents import build_excel_documents
from sportsee_llm_eval.preparation.excel import (
    PROCESSED_DIR,
    PROJECT_ROOT,
    RAW_EXCEL,
    read_dictionary,
    read_players,
    read_teams,
)
from sportsee_llm_eval.preparation.reddit import build_reddit_documents
from sportsee_llm_eval.preparation.schemas import IndexedDocument

logger = logging.getLogger(__name__)

INDEX_DIR = PROJECT_ROOT / "data" / "vector_store" / "rag_v2"
DOCUMENTS_FILE = PROCESSED_DIR / "documents_rag_v2.jsonl"
EMBEDDING_MODEL = "mistral-embed"


def build_documents(raw_excel: Path = RAW_EXCEL) -> list[IndexedDocument]:
    documents = build_excel_documents(
        read_players(raw_excel), read_teams(raw_excel), read_dictionary(raw_excel)
    )
    documents += build_reddit_documents()
    ids = [d.doc_id for d in documents]
    duplicates = [i for i, n in collections.Counter(ids).items() if n > 1]
    if duplicates:
        raise ValueError(f"Identifiants de documents en double : {duplicates[:5]}")
    return documents


def to_langchain(document: IndexedDocument) -> Document:
    metadata = document.model_dump(exclude={"text"}, exclude_none=True)
    return Document(page_content=document.text, metadata=metadata, id=document.doc_id)


def get_embeddings() -> MistralAIEmbeddings:
    load_dotenv(PROJECT_ROOT / ".env")
    return MistralAIEmbeddings(model=EMBEDDING_MODEL, max_retries=10)


def build_index(
    index_dir: Path = INDEX_DIR, documents_file: Path = DOCUMENTS_FILE
) -> FAISS:
    documents = build_documents()
    counts = collections.Counter(d.source_type for d in documents)
    logger.info("%s documents validés : %s", len(documents), dict(counts))

    documents_file.parent.mkdir(parents=True, exist_ok=True)
    with documents_file.open("w", encoding="utf-8") as f:
        for d in documents:
            f.write(d.model_dump_json() + "\n")

    logger.info("Embeddings %s et index FAISS...", EMBEDDING_MODEL)
    store = FAISS.from_documents([to_langchain(d) for d in documents], get_embeddings())
    index_dir.mkdir(parents=True, exist_ok=True)
    store.save_local(str(index_dir))
    (index_dir / "manifest.json").write_text(
        json.dumps(
            {
                "embedding_model": EMBEDDING_MODEL,
                "documents": len(documents),
                "par_type": dict(counts),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    logger.info("Index écrit dans %s (%s vecteurs)", index_dir, store.index.ntotal)
    return store


def load_index(index_dir: Path = INDEX_DIR) -> FAISS:
    # allow_dangerous_deserialization : l'index est produit localement par ce script
    return FAISS.load_local(
        str(index_dir), get_embeddings(), allow_dangerous_deserialization=True
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    argparse.ArgumentParser(description="Construction de l'index rag_v2").parse_args()
    build_index()


if __name__ == "__main__":
    main()
