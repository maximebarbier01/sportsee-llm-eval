# Évaluation RAGAS : rag_sql

- Date : 2026-10-08T16:04:59+02:00
- Questions : 26 (evaluation/questions/robustesse_v1.json)
- Système : modèle `mistral-small-latest`, température 0.0, k=5
- Juge : `mistral-large-latest` + embeddings `mistral-embed`, ragas 0.4.3
- Questions sans contexte (aucun outil appelé ou erreur API) : 1
- Questions sans aucun score (échec du juge) : 0
- Choix d'outils conforme (outils nécessaires appelés) : 20 / 20
- Intégrité de la base après l'évaluation : intacte ({'teams': 30, 'players': 569, 'stats': 569, 'report_messages': 355, 'checksum_stats': 480222})

## Scores moyens par catégorie

| catégorie | n | faithfulness | answer_relevancy | llm_context_precision_with_reference | context_recall | factual_correctness | exactitude_reponse | refus_sans_invention | refus_modification |
|---|---|---|---|---|---|---|---|---|---|
| mixte | 8 | 0.97 | 0.79 | 0.52 | 0.91 | 0.68 | 0.88 | — | — |
| arbitrage | 4 | 1.00 | 0.95 | 0.66 | 1.00 | 0.83 | 1.00 | — | — |
| piege_unite | 4 | 1.00 | 0.97 | 0.75 | 0.25 | 0.67 | 0.75 | — | — |
| homonyme | 2 | 1.00 | 0.95 | 1.00 | 0.00 | 0.32 | 0.00 | — | — |
| seuil_implicite | 2 | 1.00 | 0.97 | 1.00 | 0.50 | 0.33 | 0.50 | — | — |
| hors_couverture | 3 | — | — | — | — | 0.62 | — | 1.00 | — |
| injection | 3 | — | — | — | — | — | — | — | 1.00 |
| **global** | 26 | 0.99 | 0.89 | 0.71 | 0.66 | 0.64 | 0.75 | 1.00 | 1.00 |

`—` : métrique non applicable. Les métriques de contexte et de pertinence ne sont pas calculées sur `hors_couverture` (aucun contexte pertinent par construction, et un refus correct est noté 0 par answer_relevancy) ; `refus_sans_invention` n'est calculée que sur cette catégorie, et `refus_modification` (refus de modifier les données) que sur `injection`.
