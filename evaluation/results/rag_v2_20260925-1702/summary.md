# Évaluation RAGAS : rag_v2

- Date : 2026-09-25T17:02:09+02:00
- Questions : 32 (evaluation/questions/questions_v1.json)
- Système : modèle `mistral-small-latest`, température 0.0, k=5
- Juge : `mistral-large-latest` + embeddings `mistral-embed`, ragas 0.4.3
- Recherches vides (erreur API persistante) : 0
- Questions sans aucun score (échec du juge) : 0

## Scores moyens par catégorie

| catégorie | n | faithfulness | answer_relevancy | llm_context_precision_with_reference | context_recall | factual_correctness | exactitude_reponse | refus_sans_invention |
|---|---|---|---|---|---|---|---|---|
| simple | 7 | 0.85 | 0.79 | 0.62 | 0.71 | 0.52 | 0.71 | — |
| complexe | 7 | 0.74 | 0.81 | 0.39 | 0.48 | 0.50 | 0.43 | — |
| bruitee | 5 | 0.70 | 0.68 | 0.68 | 0.80 | 0.50 | 0.80 | — |
| texte | 6 | 0.97 | 0.95 | 0.73 | 0.94 | 0.33 | 0.83 | — |
| mixte | 3 | 0.81 | 0.93 | 0.53 | 0.67 | 0.34 | 0.67 | — |
| hors_couverture | 4 | — | — | — | — | 0.64 | — | 1.00 |
| **global** | 32 | 0.82 | 0.83 | 0.59 | 0.71 | 0.47 | 0.68 | 1.00 |

`—` : métrique non applicable. Les métriques de contexte et de pertinence ne sont pas calculées sur `hors_couverture` (aucun contexte pertinent par construction, et un refus correct est noté 0 par answer_relevancy) ; `refus_sans_invention` n'est calculée que sur cette catégorie.
