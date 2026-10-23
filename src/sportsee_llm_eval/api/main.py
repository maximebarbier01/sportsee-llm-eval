"""API REST de l'assistant SportSee (FastAPI).

Routes :
    GET  /health  état du service : base SQLite, index vectoriel, clé Mistral
    POST /ask     question en langage naturel -> réponse structurée, sources, outils appelés
    GET  /docs    documentation interactive (Swagger), générée automatiquement

Lancement :
    poetry run uvicorn sportsee_llm_eval.api.main:app --port 8000

Les assistants (rag_sql par défaut, rag_v2 en option) sont chargés au premier appel puis
gardés en mémoire : l'index FAISS et la base ne sont pas relus à chaque question. Chaque
requête est tracée dans Logfire (route, durée, puis toute la chaîne RAG / SQL).

Une panne de l'API Mistral (erreur HTTP du modèle de l'agent ou de l'outil SQL) est renvoyée
en 503 avec un message explicite, plutôt qu'en erreur 500 avec la trace Python.
"""

import os
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated, Literal, Protocol

import httpx
import logfire
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from pydantic_ai.exceptions import ModelHTTPError

from sportsee_llm_eval.observability.logfire_setup import setup_logfire
from sportsee_llm_eval.preparation.build_index import INDEX_DIR
from sportsee_llm_eval.sql.schema import DB_PATH

API_VERSION = "1.1.0"
System = Literal["rag_sql", "rag_v2"]
# erreurs de l'API Mistral : agent Pydantic AI, ou outil SQL / embeddings (clients httpx)
MISTRAL_ERRORS = (ModelHTTPError, httpx.HTTPError)


# --------------------------------------------------------------------------- schémas


class AskRequest(BaseModel):
    question: str = Field(
        min_length=3,
        max_length=500,
        description="Question en langage naturel",
        examples=["Quel joueur a le plus d'interceptions cette saison ?"],
    )
    system: System = Field(
        default="rag_sql",
        description="rag_sql : agent recherche + base SQL (recommandé) ; rag_v2 : recherche seule",
    )


class AskResponse(BaseModel):
    reponse: str = Field(description="Réponse rédigée en français")
    information_disponible: bool = Field(
        description="false si les données ne permettent pas de répondre (refus)"
    )
    sources: list[str] = Field(
        description="Identifiants des résultats utilisés (sql::N, joueur::…, reddit::…)"
    )
    outils_appeles: list[str] = Field(
        description="Outils appelés par l'agent (rag_sql)"
    )
    systeme: System
    latence_s: float = Field(
        description="Temps de traitement de la question, en secondes"
    )


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    base_sqlite: bool = Field(description="La base data/database/sportsee.db existe")
    index_vectoriel: bool = Field(description="L'index data/vector_store/rag_v2 existe")
    cle_mistral: bool = Field(description="MISTRAL_API_KEY est définie")


# --------------------------------------------------------------------------- assistants


class Assistant(Protocol):
    def ask(self, question: str) -> tuple: ...


@lru_cache(maxsize=2)
def load_assistant(system: System) -> Assistant:
    """Charge un assistant une seule fois (index et base gardés en mémoire)."""
    if system == "rag_sql":
        from sportsee_llm_eval.rag.rag_sql import RagSql

        return RagSql()
    from sportsee_llm_eval.rag.rag_v2 import RagV2

    return RagV2()


def get_assistant_loader():
    """Dépendance FastAPI : remplaçable dans les tests par un faux assistant."""
    return load_assistant


def mistral_status(error: Exception) -> int | None:
    """Code HTTP renvoyé par Mistral, s'il est connu (absent pour une erreur réseau)."""
    if isinstance(error, ModelHTTPError):
        return error.status_code
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code
    return None


def answer(assistant: Assistant, system: System, question: str) -> AskResponse:
    start = time.perf_counter()
    response, extra = assistant.ask(question)
    # rag_sql renvoie ses dépendances (outils appelés) ; rag_v2 renvoie ses documents
    tools = list(getattr(extra, "tools_called", []))
    return AskResponse(
        reponse=response.reponse,
        information_disponible=response.information_disponible,
        sources=response.sources,
        outils_appeles=tools,
        systeme=system,
        latence_s=round(time.perf_counter() - start, 2),
    )


# --------------------------------------------------------------------------- application

setup_logfire(service_name="sportsee-api")
app = FastAPI(
    title="SportSee : assistant d'analyse NBA",
    version=API_VERSION,
    description=(
        "Pose une question sur les statistiques de saison des joueurs et des équipes NBA, "
        "ou sur les discussions Reddit. L'assistant répond uniquement à partir des données "
        "SportSee, cite ses sources et déclare l'information indisponible plutôt que de "
        "l'inventer. La base est consultée en lecture seule."
    ),
)
logfire.instrument_fastapi(app)


@app.get("/health", response_model=HealthResponse, tags=["service"])
def health() -> HealthResponse:
    """État du service : les ressources nécessaires sont-elles présentes ?"""
    checks = {
        "base_sqlite": DB_PATH.exists(),
        "index_vectoriel": (INDEX_DIR / "index.faiss").exists(),
        "cle_mistral": bool(os.getenv("MISTRAL_API_KEY")),
    }
    return HealthResponse(
        status="ok" if all(checks.values()) else "degraded",
        version=API_VERSION,
        **checks,
    )


@app.post(
    "/ask",
    response_model=AskResponse,
    tags=["assistant"],
    responses={
        422: {"description": "Question invalide (vide, trop courte ou trop longue)"},
        503: {
            "description": (
                "Assistant indisponible : base, index ou clé Mistral manquants, "
                "ou API Mistral momentanément en panne"
            )
        },
    },
)
def ask(
    request: AskRequest,
    loader: Annotated[Callable[[System], Assistant], Depends(get_assistant_loader)],
) -> AskResponse:
    """Pose une question à l'assistant et renvoie une réponse structurée."""
    try:
        assistant = loader(request.system)
    except (FileNotFoundError, RuntimeError, OSError) as e:
        logfire.error("assistant indisponible", systeme=request.system, erreur=str(e))
        raise HTTPException(
            status_code=503,
            detail=f"Assistant indisponible : {e}. Vérifier GET /health.",
        ) from e
    try:
        return answer(assistant, request.system, request.question)
    except MISTRAL_ERRORS as e:
        status = mistral_status(e)
        logfire.error(
            "API Mistral en erreur",
            systeme=request.system,
            statut=status,
            erreur=str(e),
        )
        raise HTTPException(
            status_code=503,
            detail=(
                f"Service Mistral momentanément indisponible (code {status or 'réseau'}). "
                "Réessayer dans quelques minutes."
            ),
        ) from e
