# Évaluation RAGAS : rag_v2

- Date : 2026-10-08T16:30:31+02:00
- Questions : 26 (evaluation/questions/robustesse_v1.json)
- Système : modèle `mistral-small-latest`, température 0.0, k=5
- Juge : `mistral-large-latest` + embeddings `mistral-embed`, ragas 0.4.3
- Questions sans contexte (aucun outil appelé ou erreur API) : 0
- Questions sans aucun score (échec du juge) : 0

## Scores moyens par catégorie

| catégorie | n | faithfulness | answer_relevancy | llm_context_precision_with_reference | context_recall | factual_correctness | exactitude_reponse | refus_sans_invention | refus_modification |
|---|---|---|---|---|---|---|---|---|---|
| mixte | 8 | 0.94 | 0.80 | 0.59 | 0.81 | 0.61 | 0.62 | — | — |
| arbitrage | 4 | 0.92 | 0.96 | 0.45 | 1.00 | 0.63 | 1.00 | — | — |
| piege_unite | 4 | 0.92 | 0.96 | 0.67 | 0.75 | 0.60 | 0.75 | — | — |
| homonyme | 2 | 1.00 | 0.95 | 1.00 | 0.50 | 0.44 | 0.50 | — | — |
| seuil_implicite | 2 | 1.00 | 0.44 | 0.89 | 0.00 | 0.00 | 0.00 | — | — |
| hors_couverture | 3 | — | — | — | — | 0.68 | — | 1.00 | — |
| injection | 3 | — | — | — | — | — | — | — | 0.67 |
| **global** | 26 | 0.94 | 0.85 | 0.65 | 0.72 | 0.55 | 0.65 | 1.00 | 0.67 |

`—` : métrique non applicable. Les métriques de contexte et de pertinence ne sont pas calculées sur `hors_couverture` (aucun contexte pertinent par construction, et un refus correct est noté 0 par answer_relevancy) ; `refus_sans_invention` n'est calculée que sur cette catégorie, et `refus_modification` (refus de modifier les données) que sur `injection`.
