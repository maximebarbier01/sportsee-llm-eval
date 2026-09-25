"""Poser une question à l'assistant rag_v2 depuis le terminal (démonstration + trace Logfire).

Usage :
    python -m sportsee_llm_eval.rag.ask "Quel est le pourcentage à 3 points de Stephen Curry ?"
"""

import argparse
import logging

import logfire

from sportsee_llm_eval.rag.rag_v2 import RagV2


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(
        description="Question à l'assistant SportSee (rag_v2)"
    )
    parser.add_argument("question", help="Question en langage naturel")
    args = parser.parse_args()

    rag = RagV2()
    response, documents = rag.ask(args.question)

    print(f"\n{response.reponse}\n")
    print(
        f"Information disponible : {'oui' if response.information_disponible else 'non'}"
    )
    print(f"Sources citées : {', '.join(response.sources) or 'aucune'}")
    print(f"Documents fournis au modèle : {', '.join(d.id for d in documents)}")
    logfire.force_flush()  # envoie la trace avant la fin du processus


if __name__ == "__main__":
    main()
