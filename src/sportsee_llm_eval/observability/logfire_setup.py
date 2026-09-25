"""Configuration de Pydantic Logfire : traces de la chaîne RAG pas à pas.

Ce qui est tracé :
- pipeline de préparation (build_index) : un span par étape avec les volumes traités ;
- question rag_v2 : recherche vectorielle (question, k, documents retrouvés et scores,
  posts de threads ajoutés), puis agent Pydantic AI (prompt, appel Mistral, tokens,
  sortie structurée, relances du validateur de sources) ;
- appels HTTP à l'API Mistral (embeddings, chat) sous forme d'étapes de la trace ;
- évaluation : un span par question du jeu de test (identifiant, catégorie).

Les traces sont envoyées à Logfire si un jeton est disponible : LOGFIRE_TOKEN dans .env, ou
identifiants créés par « logfire projects use/new » dans .logfire/ à la racine du projet.
Sans jeton, l'instrumentation reste active mais rien ne quitte la machine.
"""

import os
from pathlib import Path

import logfire
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOGFIRE_DIR = PROJECT_ROOT / ".logfire"  # fixe : ne dépend pas du dossier de lancement
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
        config_dir=LOGFIRE_DIR,
        console=False,
        scrubbing=False,  # les questions métier ne contiennent pas de données personnelles
    )
    logfire.instrument_pydantic_ai()
    logfire.instrument_httpx()  # requêtes vers l'API Mistral (embeddings, chat)
    _configured = True
