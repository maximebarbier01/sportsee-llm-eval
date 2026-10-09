# Évaluation RAGAS : prototype

- Date : 2026-10-09T09:33:17+02:00
- Questions : 28 (evaluation/questions/robustesse_v2.json)
- Système : modèle `mistral-small-latest`, température 0.1, k=5
- Juge : `mistral-large-latest` + embeddings `mistral-embed`, ragas 0.4.3
- Questions sans contexte (aucun outil appelé ou erreur API) : 0
- Questions sans aucun score (échec du juge) : 0

## Scores moyens par catégorie

| catégorie | n | faithfulness | answer_relevancy | llm_context_precision_with_reference | context_recall | factual_correctness | exactitude_reponse | refus_sans_invention | refus_modification |
|---|---|---|---|---|---|---|---|---|---|
| mixte | 8 | 0.28 | 0.53 | 0.16 | 0.00 | 0.03 | 0.00 | — | — |
| arbitrage | 4 | 0.36 | 0.46 | 0.12 | 0.00 | 0.03 | 0.25 | — | — |
| piege_unite | 4 | 0.15 | 0.24 | 0.25 | 0.00 | 0.01 | 0.00 | — | — |
| homonyme | 3 | 0.33 | 0.00 | 0.00 | 0.00 | 0.07 | 0.00 | — | — |
| seuil_implicite | 3 | 0.41 | 0.62 | 0.86 | 0.00 | 0.04 | 0.00 | — | — |
| hors_couverture | 3 | — | — | — | — | 0.32 | — | 0.67 | — |
| injection | 3 | — | — | — | — | — | — | — | 0.33 |
| **global** | 28 | 0.30 | 0.41 | 0.24 | 0.00 | 0.07 | 0.05 | 0.67 | 0.33 |

`—` : métrique non applicable. Les métriques de contexte et de pertinence ne sont pas calculées sur `hors_couverture` (aucun contexte pertinent par construction, et un refus correct est noté 0 par answer_relevancy) ; `refus_sans_invention` n'est calculée que sur cette catégorie, et `refus_modification` (refus de modifier les données) que sur `injection`.
