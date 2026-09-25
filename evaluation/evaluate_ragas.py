"""Évaluation RAGAS d'un système RAG sur le jeu de questions gelé.

Déroulé :
    1. chargement et validation Pydantic du jeu de questions ;
    2. génération : chaque question passe par le système évalué -> answers.jsonl ;
    3. notation RAGAS (juge : mistral-large-latest, embeddings : mistral-embed) ;
    4. sorties : scores.csv (par question), summary.md (catégorie x métrique), config.json.

Exemples :
    python evaluation/evaluate_ragas.py --system prototype --limit 3
    python evaluation/evaluate_ragas.py --system prototype
    python evaluation/evaluate_ragas.py --from-answers evaluation/results/prototype_20260925-1400
"""

import argparse
import json
import logging
import os
import sys
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

EVAL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EVAL_DIR.parent
DEFAULT_QUESTIONS = EVAL_DIR / "questions" / "questions_v1.json"
RESULTS_DIR = EVAL_DIR / "results"

sys.path.insert(0, str(EVAL_DIR))
load_dotenv(PROJECT_ROOT / ".env")
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")  # pas de télémétrie ragas

# L'API « classique » de ragas (evaluate + LangchainLLMWrapper) est dépréciée au profit de
# ragas.metrics.collections, mais reste fonctionnelle en 0.4.x (version figée dans le
# pyproject) et fiable avec Mistral. On masque ces avertissements pour garder la sortie lisible.
warnings.filterwarnings("ignore", category=DeprecationWarning, message=r".*ragas.*")
warnings.filterwarnings("ignore", message=r".*langchain-community.*sunset.*")

import ragas
from langchain_mistralai import ChatMistralAI, MistralAIEmbeddings
from ragas import EvaluationDataset, RunConfig, SingleTurnSample, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    AnswerRelevancy,
    AspectCritic,
    FactualCorrectness,
    Faithfulness,
    LLMContextPrecisionWithReference,
    LLMContextRecall,
)
from schemas import Question, QuestionSet, RagAnswer

logger = logging.getLogger("evaluate_ragas")

HORS_COUVERTURE = "hors_couverture"
REFUS_METRIC = "refus_sans_invention"
EXACTITUDE_METRIC = "exactitude_reponse"

# Ordre des colonnes des tableaux de sortie
METRIC_COLUMNS = [
    "faithfulness",
    "answer_relevancy",
    "llm_context_precision_with_reference",
    "context_recall",
    "factual_correctness",
    EXACTITUDE_METRIC,
    REFUS_METRIC,
]
CATEGORY_ORDER = ["simple", "complexe", "bruitee", "texte", "mixte", HORS_COUVERTURE]


# --------------------------------------------------------------------------- questions


def load_questions(
    path: Path, categories: list[str] | None, limit: int | None
) -> list[Question]:
    question_set = QuestionSet.model_validate_json(path.read_text(encoding="utf-8"))
    questions = question_set.questions
    if categories:
        questions = [q for q in questions if q.categorie in categories]
    if limit:
        questions = questions[:limit]
    logger.info(
        "%s questions chargées depuis %s (version %s)",
        len(questions),
        path.name,
        question_set.version,
    )
    return questions


# --------------------------------------------------------------------------- génération


def get_runner(system: str):
    if system == "prototype":
        from prototype_runner import PrototypeRunner

        return PrototypeRunner()
    raise ValueError(f"Système inconnu : {system}")


def generate_answers(
    runner, questions: list[Question], answers_path: Path
) -> list[RagAnswer]:
    answers = []
    with answers_path.open("w", encoding="utf-8") as f:
        for i, q in enumerate(questions, start=1):
            start = time.perf_counter()
            output = runner.answer(q.question)
            answer = RagAnswer(
                id=q.id,
                categorie=q.categorie,
                question=q.question,
                ground_truth=q.ground_truth,
                latency_s=round(time.perf_counter() - start, 2),
                **output.model_dump(),
            )
            f.write(answer.model_dump_json() + "\n")
            f.flush()  # une question déjà générée n'est pas perdue en cas d'arrêt
            answers.append(answer)
            logger.info(
                "[%s/%s] %s générée en %.1fs", i, len(questions), q.id, answer.latency_s
            )
    return answers


def load_answers(answers_path: Path) -> list[RagAnswer]:
    with answers_path.open(encoding="utf-8") as f:
        return [RagAnswer.model_validate_json(line) for line in f if line.strip()]


# --------------------------------------------------------------------------- notation


class JudgeChatMistralAI(ChatMistralAI):
    """ChatMistralAI corrigé pour le juge RAGAS.

    Bug de langchain-mistralai : _combine_llm_outputs additionne les token_usage avec +=,
    ce qui plante (TypeError dict += dict) sur les sous-dictionnaires désormais renvoyés
    par l'API Mistral (détails des tokens). Il survient dès que plusieurs générations sont
    combinées, ce que fait AnswerRelevancy (strictness=3). On ne cumule que les compteurs
    numériques.
    """

    def _combine_llm_outputs(self, llm_outputs: list[dict | None]) -> dict:
        usage: dict = {}
        for output in llm_outputs:
            for k, v in ((output or {}).get("token_usage") or {}).items():
                if isinstance(v, int | float):
                    usage[k] = usage.get(k, 0) + v
        return {"token_usage": usage, "model_name": self.model}


def build_judge(
    judge_model: str,
) -> tuple[LangchainLLMWrapper, LangchainEmbeddingsWrapper]:
    llm = JudgeChatMistralAI(model=judge_model, temperature=0, max_retries=5)
    embeddings = MistralAIEmbeddings(model="mistral-embed")
    return LangchainLLMWrapper(llm), LangchainEmbeddingsWrapper(embeddings)


def to_dataset(answers: list[RagAnswer]) -> EvaluationDataset:
    return EvaluationDataset(
        samples=[
            SingleTurnSample(
                user_input=a.question,
                response=a.answer,
                retrieved_contexts=a.contexts,
                reference=a.ground_truth,
            )
            for a in answers
        ]
    )


def score(answers: list[RagAnswer], judge_model: str, max_workers: int) -> pd.DataFrame:
    """Note les réponses. Les questions hors couverture ont leur propre jeu de métriques :
    aucun contexte n'y est pertinent par construction, et une bonne réponse est un refus
    (qu'AnswerRelevancy classe « non engagée » et note 0). On y mesure donc l'exactitude
    par rapport à la référence et un critère binaire « refuse sans inventer ».

    exactitude_reponse complète factual_correctness : ce dernier (F1 sur des affirmations
    atomiques) tombe à 0 dès que la réponse est verbeuse, même quand le chiffre attendu est
    juste (précision nulle sur les phrases annexes « selon la feuille Analyse... »).
    exactitude_reponse juge seulement si l'information principale attendue est correcte.
    """
    llm, embeddings = build_judge(judge_model)
    run_config = RunConfig(
        max_workers=max_workers, timeout=180, max_retries=10, max_wait=60
    )

    groups = {
        "couvertes": (
            [a for a in answers if a.categorie != HORS_COUVERTURE],
            [
                Faithfulness(),
                AnswerRelevancy(),
                LLMContextPrecisionWithReference(),
                LLMContextRecall(),
                FactualCorrectness(),
                AspectCritic(
                    name=EXACTITUDE_METRIC,
                    definition=(
                        "Compare la réponse à la réponse de référence. Renvoie 1 si la réponse "
                        "donne la même information principale que la référence (mêmes joueurs, "
                        "équipes et valeurs chiffrées, aux arrondis et formats de nombre près, "
                        "ex. 2 485 = 2485), même si elle ajoute d'autres détails ou omet des "
                        "précisions secondaires. Renvoie 0 si l'information principale est "
                        "absente, différente ou inventée."
                    ),
                ),
            ],
        ),
        HORS_COUVERTURE: (
            [a for a in answers if a.categorie == HORS_COUVERTURE],
            [
                FactualCorrectness(),
                AspectCritic(
                    name=REFUS_METRIC,
                    definition=(
                        "Renvoie 1 si la réponse indique clairement que l'information demandée "
                        "n'est pas disponible dans les données, SANS inventer de chiffres, de noms "
                        "ou de faits pour y répondre quand même. Renvoie 0 sinon."
                    ),
                ),
            ],
        ),
    }

    frames = []
    for label, (subset, metrics) in groups.items():
        if not subset:
            continue
        logger.info(
            "Notation RAGAS : %s questions (%s), %s métriques",
            len(subset),
            label,
            len(metrics),
        )
        result = evaluate(
            dataset=to_dataset(subset),
            metrics=metrics,
            llm=llm,
            embeddings=embeddings,
            run_config=run_config,
            raise_exceptions=False,
        )
        # ragas suffixe certains noms de colonnes par leurs paramètres
        # (ex. « factual_correctness(mode=f1) ») : on normalise sur le nom de la métrique
        df = result.to_pandas().rename(columns=lambda c: c.split("(")[0])
        df.insert(0, "id", [a.id for a in subset])
        df.insert(1, "categorie", [a.categorie for a in subset])
        frames.append(df)

    scores = pd.concat(frames, ignore_index=True)
    for col in METRIC_COLUMNS:
        if col not in scores.columns:
            scores[col] = float("nan")
    meta = pd.DataFrame(
        [
            {"id": a.id, "retrieval_empty": a.retrieval_empty, "latency_s": a.latency_s}
            for a in answers
        ]
    )
    return scores.merge(meta, on="id", how="left")


# --------------------------------------------------------------------------- restitution


def build_summary(scores: pd.DataFrame) -> pd.DataFrame:
    summary = scores.groupby("categorie")[METRIC_COLUMNS].mean()
    summary.insert(0, "n", scores.groupby("categorie").size())
    summary = summary.reindex([c for c in CATEGORY_ORDER if c in summary.index])
    overall = scores[METRIC_COLUMNS].mean().to_frame().T
    overall.insert(0, "n", len(scores))
    overall.index = ["**global**"]
    return pd.concat([summary, overall])


def to_markdown(df: pd.DataFrame) -> str:
    headers = [df.index.name or "catégorie", *df.columns]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for idx, row in df.iterrows():
        cells = [str(idx)]
        for col, val in row.items():
            if col == "n":
                cells.append(str(int(val)))
            else:
                cells.append("—" if pd.isna(val) else f"{val:.2f}")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_outputs(out_dir: Path, scores: pd.DataFrame, config: dict) -> None:
    scores.to_csv(out_dir / "scores.csv", index=False)
    summary = build_summary(scores)
    n_errors = int(scores[METRIC_COLUMNS].isna().all(axis=1).sum())
    n_empty = int(scores["retrieval_empty"].sum())
    md = [
        f"# Évaluation RAGAS : {config['system']['system']}",
        "",
        f"- Date : {config['date']}",
        f"- Questions : {len(scores)} ({config['questions_file']})",
        f"- Système : modèle `{config['system']['model']}`, température {config['system']['temperature']}, k={config['system']['k']}",
        f"- Juge : `{config['judge_model']}` + embeddings `mistral-embed`, ragas {config['ragas_version']}",
        f"- Recherches vides (erreur API persistante) : {n_empty}",
        f"- Questions sans aucun score (échec du juge) : {n_errors}",
        "",
        "## Scores moyens par catégorie",
        "",
        to_markdown(summary),
        "",
        (
            "`—` : métrique non applicable. Les métriques de contexte et de pertinence ne sont pas "
            f"calculées sur `{HORS_COUVERTURE}` (aucun contexte pertinent par construction, et un refus "
            f"correct est noté 0 par answer_relevancy) ; `{REFUS_METRIC}` n'est calculée que sur cette catégorie."
        ),
        "",
    ]
    (out_dir / "summary.md").write_text("\n".join(md), encoding="utf-8")
    (out_dir / "config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\n" + to_markdown(summary) + "\n")
    logger.info("Résultats écrits dans %s", out_dir.relative_to(PROJECT_ROOT))


# --------------------------------------------------------------------------- main


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Évaluation RAGAS d'un système RAG SportSee"
    )
    parser.add_argument(
        "--system", default="prototype", choices=["prototype"], help="Système à évaluer"
    )
    parser.add_argument(
        "--questions",
        type=Path,
        default=DEFAULT_QUESTIONS,
        help="Jeu de questions (JSON)",
    )
    parser.add_argument(
        "--categories",
        type=lambda s: s.split(","),
        help="Filtrer : ex. simple,complexe",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="N'évaluer que les N premières questions (test rapide)",
    )
    parser.add_argument(
        "--judge", default="mistral-large-latest", help="Modèle Mistral juge"
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=2,
        help="Appels parallèles au juge (bas pour limiter les erreurs 429 Mistral)",
    )
    parser.add_argument(
        "--from-answers",
        type=Path,
        help="Dossier de résultats existant : renote answers.jsonl sans régénérer",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    args = parse_args()

    if args.from_answers:
        out_dir = args.from_answers
        config = json.loads((out_dir / "config.json").read_text(encoding="utf-8"))
        answers = load_answers(out_dir / "answers.jsonl")
        logger.info("%s réponses rechargées depuis %s", len(answers), out_dir)
    else:
        questions = load_questions(args.questions, args.categories, args.limit)
        runner = get_runner(args.system)
        stamp = datetime.now(UTC).astimezone().strftime("%Y%m%d-%H%M")
        suffix = f"_limit{args.limit}" if args.limit else ""
        out_dir = RESULTS_DIR / f"{runner.name}_{stamp}{suffix}"
        out_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "date": datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
            "questions_file": str(args.questions.relative_to(PROJECT_ROOT)),
            "question_ids": [q.id for q in questions],
            "system": runner.config(),
        }
        # config écrite avant la génération : --from-answers reste possible si la notation échoue
        (out_dir / "config.json").write_text(
            json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        answers = generate_answers(runner, questions, out_dir / "answers.jsonl")

    config.update({"judge_model": args.judge, "ragas_version": ragas.__version__})
    scores = score(answers, args.judge, args.max_workers)
    write_outputs(out_dir, scores, config)


if __name__ == "__main__":
    main()
