"""Configuration de Pydantic Logfire : traces de la chaîne RAG pas à pas.

Chaque question produit une trace contenant la recherche vectorielle (question, k, documents
retrouvés avec leur score) puis l'exécution de l'agent Pydantic AI (prompt, appel Mistral,
tokens, sortie structurée et éventuelles relances de validation).

Les traces sont envoyées à Logfire seulement si LOGFIRE_TOKEN est défini dans .env ;
sans jeton, l'instrumentation est active mais rien ne quitte la machine.
"""

import os
from pathlib import Path

import logfire
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
_configured = False


def setup_logfire(service_name: str = "sportsee-rag") -> None:
    """Idempotent : peut être appelé par chaque point d'entrée sans double configuration."""
    global _configured
    if _configured:
        return
    load_dotenv(PROJECT_ROOT / ".env")
    logfire.configure(
        service_name=service_name,
        send_to_logfire="if-token-present",
        token=os.getenv("LOGFIRE_TOKEN") or None,
        console=False,
        scrubbing=False,  # les questions métier ne contiennent pas de données personnelles
    )
    logfire.instrument_pydantic_ai()
    _configured = True
