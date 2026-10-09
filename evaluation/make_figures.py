"""Graphiques du rapport, générés à partir des résultats d'évaluation (evaluation/results/).

Chaque figure est recalculée depuis les scores.csv / answers.jsonl : relancer une
évaluation puis ce script met le rapport à jour. Sorties : docs/figures/*.png.

Usage :
    python evaluation/make_figures.py
"""

import json
import pickle
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evaluation" / "results"
OUT = ROOT / "docs" / "figures"

SYSTEMS = ["prototype", "rag_v2", "rag_sql"]
LABELS = {
    "prototype": "Prototype",
    "rag_v2": "rag_v2 (pipeline)",
    "rag_sql": "rag_sql (+ SQL)",
}
# couleur attachée au système (jamais au rang), 3 premiers créneaux de la palette de référence
COLORS = {"rag_sql": "#2a78d6", "rag_v2": "#eb6834", "prototype": "#1baf7a"}
NEUTRAL = "#b4b2a9"  # référence « avant »
INK, INK_2, GRID = "#1f2328", "#57606a", "#e4e6e8"

CATEGORY_LABELS = {
    "simple": "Simple",
    "complexe": "Complexe",
    "bruitee": "Bruitée",
    "texte": "Texte (Reddit)",
    "mixte": "Mixte",
    "hors_couverture": "Hors couverture",
    "arbitrage": "Arbitrage",
    "piege_unite": "Piège d'unité",
    "homonyme": "Homonyme",
    "seuil_implicite": "Seuil implicite",
    "injection": "Injection",
}
METRIC_LABELS = {
    "exactitude_reponse": "Exactitude",
    "faithfulness": "Fidélité",
    "context_recall": "Rappel\ndu contexte",
    "llm_context_precision_with_reference": "Précision\ndu contexte",
    "answer_relevancy": "Pertinence",
    "factual_correctness": "Factual correctness",
}

mpl.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_2,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": False,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
    }
)


def latest(system: str, question_set: str = "") -> Path:
    """Dernier dossier de résultats complet d'un système sur un jeu de questions."""
    prefix = f"{system}_{question_set}_" if question_set else f"{system}_2"
    runs = sorted(d for d in RESULTS.glob(f"{prefix}*") if "limit" not in d.name)
    if not runs:
        raise FileNotFoundError(f"Aucun résultat pour {system} {question_set}")
    return runs[-1]


def scores(system: str, question_set: str = "") -> pd.DataFrame:
    return pd.read_csv(latest(system, question_set) / "scores.csv")


def main_score(df: pd.DataFrame) -> pd.Series:
    """Exactitude, ou refus correct pour les catégories où la bonne réponse est un refus."""
    s = df["exactitude_reponse"].copy()
    for col in ("refus_sans_invention", "refus_modification"):
        if col in df:
            s = s.fillna(df[col])
    return s


def style_axis(ax, ymax: float = 1.0) -> None:
    ax.set_ylim(0, ymax)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", length=0)


def grouped_bars(
    ax,
    categories,
    series: dict[str, list[float]],
    colors: dict,
    labels: dict,
    labelled: set[str] | None = None,
):
    """Barres groupées ; valeurs affichées seulement pour les séries de `labelled`
    (toutes par défaut) : étiquettes sélectives quand les barres sont serrées."""
    n = len(series)
    width = 0.8 / n
    for i, (key, values) in enumerate(series.items()):
        xs = [c + (i - (n - 1) / 2) * width for c in range(len(categories))]
        bars = ax.bar(
            xs,
            values,
            width=width * 0.92,  # espace entre barres adjacentes
            color=colors[key],
            label=labels[key],
            edgecolor="white",
            linewidth=1,
        )
        if labelled is not None and key not in labelled:
            continue
        for bar, v in zip(bars, values, strict=True):
            if pd.notna(v):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    v + 0.015,
                    f"{v:.2f}".replace(".", ","),
                    ha="center",
                    va="bottom",
                    fontsize=7,
                    color=INK_2,
                )
    ax.set_xticks(range(len(categories)))
    ax.set_xticklabels(
        [CATEGORY_LABELS.get(c, METRIC_LABELS.get(c, c)) for c in categories]
    )


def _legend_above(ax) -> None:
    ax.legend(
        frameon=False, ncol=3, loc="lower left", bbox_to_anchor=(0, 1.0), fontsize=8
    )
    # titre remonté au-dessus de la légende (marge), sinon ils se chevauchent
    ax.set_title(ax.get_title(loc="left"), loc="left", color=INK, pad=26)


def _pct(x: float) -> str:
    return f"{x:.1%}" if 0 < x < 0.01 else f"{x:.0%}"


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name)
    plt.close(fig)
    print(f"docs/figures/{name}")


def fig_exactitude_par_categorie() -> None:
    cats = ["simple", "complexe", "bruitee", "texte", "mixte", "hors_couverture"]
    series = {}
    for sysname in SYSTEMS:
        df = scores(sysname)
        series[sysname] = (
            main_score(df).groupby(df["categorie"]).mean().reindex(cats).tolist()
        )
    fig, ax = plt.subplots(figsize=(8, 3.4))
    grouped_bars(ax, cats, series, COLORS, LABELS)
    style_axis(ax, 1.12)
    ax.set_ylabel("Exactitude (refus correct pour « hors couverture »)")
    ax.set_title(
        "Exactitude par catégorie, jeu principal (32 questions)", loc="left", color=INK
    )
    _legend_above(ax)
    save(fig, "exactitude_par_categorie.png")


def fig_metriques_globales() -> None:
    metrics = [
        "exactitude_reponse",
        "faithfulness",
        "context_recall",
        "llm_context_precision_with_reference",
        "answer_relevancy",
    ]
    series = {s: scores(s)[metrics].mean().tolist() for s in SYSTEMS}
    fig, ax = plt.subplots(figsize=(8, 3.2))
    grouped_bars(ax, metrics, series, COLORS, LABELS)
    style_axis(ax, 1.12)
    ax.set_title(
        "Métriques moyennes, jeu principal (32 questions)", loc="left", color=INK
    )
    _legend_above(ax)
    save(fig, "metriques_globales.png")


def fig_provenance_prototype() -> None:
    """Part de chaque source dans l'index du prototype et dans les extraits récupérés."""
    chunks = pickle.load(
        (ROOT / "data" / "vector_store" / "prototype" / "document_chunks.pkl").open(
            "rb"
        )
    )

    def group(source: str) -> str:
        if source.startswith("Reddit"):
            return "Reddit 1-4"
        if "Analyse" in source:
            return "Analyse + Analyse Vide"
        return source.split("Feuille: ")[-1].rstrip(")")

    by_text = {c["text"]: group(c["metadata"]["source"]) for c in chunks}
    index = pd.Series([group(c["metadata"]["source"]) for c in chunks]).value_counts()
    answers = latest("prototype") / "answers.jsonl"
    retrieved = pd.Series(
        [by_text[t] for line in answers.open() for t in json.loads(line)["contexts"]]
    ).value_counts()
    order = [
        "Données NBA",
        "Reddit 1-4",
        "Analyse + Analyse Vide",
        "Dictionnaire des données",
        "Equipe",
    ]
    idx = (index.reindex(order).fillna(0) / index.sum()).tolist()
    ret = (retrieved.reindex(order).fillna(0) / retrieved.sum()).tolist()

    fig, ax = plt.subplots(figsize=(8, 2.9))
    ys = range(len(order))
    h = 0.38
    ax.barh(
        [y - h / 2 for y in ys],
        idx,
        height=h * 0.92,
        color=NEUTRAL,
        label="Part de l'index (302 extraits)",
    )
    ax.barh(
        [y + h / 2 for y in ys],
        ret,
        height=h * 0.92,
        color=COLORS["prototype"],
        label=f"Part des extraits récupérés ({int(retrieved.sum())})",
    )
    for y, a, b in zip(ys, idx, ret, strict=True):
        ax.text(a + 0.006, y - h / 2, _pct(a), va="center", fontsize=7, color=INK_2)
        ax.text(b + 0.006, y + h / 2, _pct(b), va="center", fontsize=7, color=INK_2)
    ax.set_yticks(list(ys))
    ax.set_yticklabels(order)
    ax.invert_yaxis()
    ax.set_xlim(0, 0.6)
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0))
    ax.xaxis.grid(True, color=GRID)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.set_title(
        "Prototype : la feuille des statistiques n'est jamais retrouvée",
        loc="left",
        color=INK,
    )
    ax.legend(frameon=False, loc="lower right")
    save(fig, "provenance_prototype.png")


def fig_robustesse() -> None:
    cats = [
        "mixte",
        "arbitrage",
        "piege_unite",
        "homonyme",
        "seuil_implicite",
        "injection",
        "hors_couverture",
    ]
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.4), sharey=True)
    for ax, (qset, title) in zip(
        axes,
        [
            ("robustesse_v1", "Robustesse v1 : diagnostic (26 questions)"),
            ("robustesse_v2", "Robustesse v2 : validation après corrections (28)"),
        ],
        strict=True,
    ):
        series = {}
        for sysname in SYSTEMS:
            df = scores(sysname, qset)
            series[sysname] = (
                main_score(df).groupby(df["categorie"]).mean().reindex(cats).tolist()
            )
        grouped_bars(ax, cats, series, COLORS, LABELS, labelled={"rag_sql"})
        style_axis(ax, 1.15)
        ax.set_title(title, loc="left", color=INK, fontsize=9)
        ax.tick_params(axis="x", labelrotation=35)
        for label in ax.get_xticklabels():
            label.set_ha("right")
    axes[0].set_ylabel("Score (verdicts du juge)")
    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        legend_labels,
        frameon=False,
        ncol=3,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.2),
    )
    fig.text(
        0.5,
        -0.25,
        "Valeurs affichées pour rag_sql ; détail par système dans le rapport.",
        ha="center",
        fontsize=7,
        color=INK_2,
    )
    save(fig, "robustesse.png")


def fig_latence() -> None:
    sets = [
        ("", "Jeu principal"),
        ("robustesse_v1", "Robustesse v1"),
        ("robustesse_v2", "Robustesse v2"),
    ]
    series = {s: [scores(s, q)["latency_s"].mean() for q, _ in sets] for s in SYSTEMS}
    fig, ax = plt.subplots(figsize=(6.5, 2.8))
    grouped_bars(ax, [label for _, label in sets], series, COLORS, LABELS)
    for text in ax.texts:  # secondes, pas de score
        text.set_text(text.get_text() + " s")
    style_axis(ax, 5.2)
    ax.set_ylabel("Latence moyenne (s)")
    ax.set_title("Latence moyenne par question", loc="left", color=INK)
    _legend_above(ax)
    save(fig, "latence.png")


def main() -> None:
    fig_exactitude_par_categorie()
    fig_metriques_globales()
    fig_provenance_prototype()
    fig_robustesse()
    fig_latence()


if __name__ == "__main__":
    main()
