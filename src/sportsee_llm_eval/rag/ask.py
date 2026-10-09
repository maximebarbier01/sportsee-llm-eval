"""Poser une question à l'assistant depuis le terminal (démonstration + trace Logfire).

Usage :
    python -m sportsee_llm_eval.rag.ask "Quel joueur a le plus d'interceptions ?"
    python -m sportsee_llm_eval.rag.ask --system rag_v2 "Que mesure le PIE ?"
"""

import argparse
import logging

import logfire


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(description="Question à l'assistant SportSee")
    parser.add_argument("question", help="Question en langage naturel")
    parser.add_argument(
        "--system",
        choices=["rag_sql", "rag_v2"],
        default="rag_sql",
        help="rag_sql : agent avec recherche + outil SQL (défaut) ; rag_v2 : recherche seule",
    )
    args = parser.parse_args()

    if args.system == "rag_sql":
        from sportsee_llm_eval.rag.rag_sql import RagSql

        response, deps = RagSql().ask(args.question)
        details = f"Outils appelés : {', '.join(deps.tools_called) or 'aucun'}"
    else:
        from sportsee_llm_eval.rag.rag_v2 import RagV2

        response, documents = RagV2().ask(args.question)
        details = f"Documents fournis au modèle : {', '.join(d.id for d in documents)}"

    print(f"\n{response.reponse}\n")
    print(
        f"Information disponible : {'oui' if response.information_disponible else 'non'}"
    )
    print(f"Sources citées : {', '.join(response.sources) or 'aucune'}")
    print(details)
    logfire.force_flush()  # envoie la trace avant la fin du processus


if __name__ == "__main__":
    main()
