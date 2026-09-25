"""Adaptateur d'évaluation du prototype : rejoue la chaîne RAG de prototype/MistralChat.py.

MistralChat.py est un script Streamlit (l'importer lancerait l'interface), sa logique RAG
n'est pas exposée en fonction. Cet adaptateur reproduit la même chaîne sans modifier le
prototype :
    recherche FAISS (k=SEARCH_K) -> formatage du contexte -> prompt -> mistral-small.

Le prompt et la température ne sont PAS recopiés : ils sont lus dans le code source de
MistralChat.py (analyse AST), pour garantir que l'on évalue exactement le prototype.

Seule différence volontaire, propre au banc d'essai : les erreurs réseau/quota de l'API
(429, 5xx) sont relancées au lieu de produire le message d'excuse du prototype, qui
fausserait les scores sans rien dire de la qualité du RAG.
"""

import ast
import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from mistralai.client import Mistral
from mistralai.client.errors import MistralError
from schemas import RagOutput

PROTOTYPE_DIR = Path(__file__).resolve().parents[1] / "prototype"
MISTRAL_CHAT_FILE = PROTOTYPE_DIR / "MistralChat.py"

sys.path.insert(
    0, str(PROTOTYPE_DIR)
)  # rend le package `utils` du prototype importable

from utils.config import MISTRAL_API_KEY, MODEL_NAME, SEARCH_K
from utils.vector_store import VectorStoreManager

logger = logging.getLogger(__name__)

# Repris à l'identique de MistralChat.py (étapes 4 du bloc « logique RAG »)
CONTEXT_SEPARATOR = "\n\n---\n\n"
NO_CONTEXT_MESSAGE = "Aucune information pertinente trouvée dans la base de connaissances pour cette question."

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5

T = TypeVar("T")


def _parse_prototype() -> ast.Module:
    return ast.parse(MISTRAL_CHAT_FILE.read_text(encoding="utf-8"))


def load_prototype_prompt() -> str:
    """Extrait le template SYSTEM_PROMPT de MistralChat.py, sans exécuter le fichier.

    Le prototype le définit en f-string sans interpolation (accolades doublées) : sa valeur
    est donc une chaîne constante contenant les champs {context_str} et {question}.
    """
    for node in ast.walk(_parse_prototype()):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "SYSTEM_PROMPT" for t in node.targets
        ):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
            if isinstance(value, ast.JoinedStr) and all(
                isinstance(part, ast.Constant) for part in value.values
            ):
                return "".join(part.value for part in value.values)
            raise ValueError(
                "SYSTEM_PROMPT contient des expressions interpolées : extraction impossible"
            )
    raise ValueError(f"SYSTEM_PROMPT introuvable dans {MISTRAL_CHAT_FILE}")


def load_prototype_temperature() -> float:
    """Extrait la température passée à client.chat.complete(...) dans MistralChat.py."""
    for node in ast.walk(_parse_prototype()):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "complete"
        ):
            for kw in node.keywords:
                if kw.arg == "temperature":
                    return float(ast.literal_eval(kw.value))
    raise ValueError(
        f"Appel chat.complete(temperature=...) introuvable dans {MISTRAL_CHAT_FILE}"
    )


def format_context(search_results: list[dict]) -> str:
    """Formatage du contexte identique à MistralChat.py."""
    if not search_results:
        return NO_CONTEXT_MESSAGE
    return CONTEXT_SEPARATOR.join(
        f"Source: {res['metadata'].get('source', 'Inconnue')} (Score: {res['score']:.1f}%)\nContenu: {res['text']}"
        for res in search_results
    )


def _with_retry(call: Callable[[], T], what: str) -> T:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return call()
        except MistralError as e:
            if e.status_code not in RETRYABLE_STATUS or attempt == MAX_ATTEMPTS:
                raise
            wait = 2**attempt
            logger.warning(
                "%s : erreur %s, nouvel essai dans %ss (%s/%s)",
                what,
                e.status_code,
                wait,
                attempt,
                MAX_ATTEMPTS,
            )
            time.sleep(wait)
    raise AssertionError("inatteignable")


class PrototypeRunner:
    """Système « prototype » : index FAISS d'origine + prompt et paramètres de MistralChat.py."""

    name = "prototype"

    def __init__(self) -> None:
        if not MISTRAL_API_KEY:
            raise RuntimeError("MISTRAL_API_KEY absente du fichier .env")
        self.vector_store = VectorStoreManager()
        if self.vector_store.index is None or not self.vector_store.document_chunks:
            raise RuntimeError(
                "Index FAISS du prototype introuvable dans data/vector_store/prototype/"
            )
        self.client = Mistral(api_key=MISTRAL_API_KEY)
        self.prompt_template = load_prototype_prompt()
        self.temperature = load_prototype_temperature()
        self.model = MODEL_NAME
        self.k = SEARCH_K

    def config(self) -> dict:
        return {
            "system": self.name,
            "model": self.model,
            "temperature": self.temperature,
            "k": self.k,
            "index_vectors": self.vector_store.index.ntotal,
        }

    def _search(self, question: str) -> list[dict]:
        # VectorStoreManager.search avale les erreurs API et renvoie [] ; sans min_score,
        # une liste vide sur un index non vide ne peut venir que d'une erreur : on relance.
        for attempt in range(1, MAX_ATTEMPTS + 1):
            results = self.vector_store.search(question, k=self.k)
            if results:
                return results
            if attempt < MAX_ATTEMPTS:
                wait = 2**attempt
                logger.warning(
                    "Recherche vide (probable erreur API), nouvel essai dans %ss", wait
                )
                time.sleep(wait)
        return []

    def answer(self, question: str) -> RagOutput:
        results = self._search(question)
        prompt = self.prompt_template.format(
            context_str=format_context(results), question=question
        )
        response = _with_retry(
            lambda: self.client.chat.complete(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
            ),
            "Génération",
        )
        return RagOutput(
            answer=response.choices[0].message.content,
            contexts=[res["text"] for res in results],
            retrieval_empty=not results,
        )
