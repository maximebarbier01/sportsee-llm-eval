# Évaluation RAGAS : prototype

- Date : 2026-09-25T11:55:20+02:00
- Questions : 32 (evaluation/questions/questions_v1.json)
- Système : modèle `mistral-small-latest`, température 0.1, k=5
- Juge : `mistral-large-latest` + embeddings `mistral-embed`, ragas 0.4.3
- Recherches vides (erreur API persistante) : 0
- Questions sans aucun score (échec du juge) : 0

## Scores moyens par catégorie

| catégorie | n | faithfulness | answer_relevancy | llm_context_precision_with_reference | context_recall | factual_correctness | exactitude_reponse | refus_sans_invention |
|---|---|---|---|---|---|---|---|---|
| simple | 7 | 0.34 | 0.65 | 0.55 | 0.40 | 0.15 | 0.57 | — |
| complexe | 7 | 0.18 | 0.79 | 0.24 | 0.00 | 0.09 | 0.14 | — |
| bruitee | 5 | 0.15 | 0.48 | 0.40 | 0.40 | 0.08 | 0.20 | — |
| texte | 6 | 0.55 | 0.76 | 0.66 | 0.42 | 0.26 | 0.83 | — |
| mixte | 3 | 0.17 | 0.86 | 0.17 | 0.00 | 0.01 | 0.00 | — |
| hors_couverture | 4 | — | — | — | — | 0.11 | — | 0.25 |
| **global** | 32 | 0.29 | 0.70 | 0.43 | 0.26 | 0.13 | 0.39 | 0.25 |

`—` : métrique non applicable. Les métriques de contexte et de pertinence ne sont pas calculées sur `hors_couverture` (aucun contexte pertinent par construction, et un refus correct est noté 0 par answer_relevancy) ; `refus_sans_invention` n'est calculée que sur cette catégorie.
