# Évaluation RAGAS : rag_v2

- Date : 2026-10-09T09:07:09+02:00
- Questions : 28 (evaluation/questions/robustesse_v2.json)
- Système : modèle `mistral-small-latest`, température 0.0, k=5
- Juge : `mistral-large-latest` + embeddings `mistral-embed`, ragas 0.4.3
- Questions sans contexte (aucun outil appelé ou erreur API) : 0
- Questions sans aucun score (échec du juge) : 0

## Scores moyens par catégorie

| catégorie | n | faithfulness | answer_relevancy | llm_context_precision_with_reference | context_recall | factual_correctness | exactitude_reponse | refus_sans_invention | refus_modification |
|---|---|---|---|---|---|---|---|---|---|
| mixte | 8 | 0.96 | 0.66 | 0.75 | 0.88 | 0.51 | 0.62 | — | — |
| arbitrage | 4 | 1.00 | 0.71 | 0.61 | 0.75 | 0.55 | 0.75 | — | — |
| piege_unite | 4 | 1.00 | 0.97 | 0.75 | 0.75 | 0.29 | 0.75 | — | — |
| homonyme | 3 | 0.89 | 0.89 | 0.78 | 0.83 | 0.53 | 0.67 | — | — |
| seuil_implicite | 3 | 0.77 | 0.00 | 0.94 | 0.00 | 0.13 | 0.00 | — | — |
| hors_couverture | 3 | — | — | — | — | 0.57 | — | 1.00 | — |
| injection | 3 | — | — | — | — | — | — | — | 1.00 |
| **global** | 28 | 0.94 | 0.67 | 0.75 | 0.70 | 0.45 | 0.59 | 1.00 | 1.00 |

`—` : métrique non applicable. Les métriques de contexte et de pertinence ne sont pas calculées sur `hors_couverture` (aucun contexte pertinent par construction, et un refus correct est noté 0 par answer_relevancy) ; `refus_sans_invention` n'est calculée que sur cette catégorie, et `refus_modification` (refus de modifier les données) que sur `injection`.
