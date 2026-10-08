# Évaluation RAGAS : rag_sql

- Date : 2026-10-08T15:00:34+02:00
- Questions : 32 (evaluation/questions/questions_v1.json)
- Système : modèle `mistral-small-latest`, température 0.0, k=5
- Juge : `mistral-large-latest` + embeddings `mistral-embed`, ragas 0.4.3
- Questions sans contexte (aucun outil appelé ou erreur API) : 0
- Questions sans aucun score (échec du juge) : 0

## Scores moyens par catégorie

| catégorie | n | faithfulness | answer_relevancy | llm_context_precision_with_reference | context_recall | factual_correctness | exactitude_reponse | refus_sans_invention |
|---|---|---|---|---|---|---|---|---|
| simple | 7 | 1.00 | 0.92 | 0.98 | 0.74 | 0.70 | 1.00 | — |
| complexe | 7 | 0.96 | 0.96 | 1.00 | 0.52 | 0.59 | 1.00 | — |
| bruitee | 5 | 1.00 | 0.82 | 0.82 | 1.00 | 0.82 | 1.00 | — |
| texte | 6 | 0.83 | 0.80 | 0.70 | 1.00 | 0.46 | 0.83 | — |
| mixte | 3 | 0.87 | 0.89 | 0.46 | 1.00 | 0.54 | 0.67 | — |
| hors_couverture | 4 | — | — | — | — | 0.57 | — | 1.00 |
| **global** | 32 | 0.94 | 0.88 | 0.84 | 0.82 | 0.61 | 0.93 | 1.00 |

`—` : métrique non applicable. Les métriques de contexte et de pertinence ne sont pas calculées sur `hors_couverture` (aucun contexte pertinent par construction, et un refus correct est noté 0 par answer_relevancy) ; `refus_sans_invention` n'est calculée que sur cette catégorie.
