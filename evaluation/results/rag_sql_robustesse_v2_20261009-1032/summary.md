# Évaluation RAGAS : rag_sql

- Date : 2026-10-09T10:32:14+02:00
- Questions : 28 (evaluation/questions/robustesse_v2.json)
- Système : modèle `mistral-small-latest`, température 0.0, k=5
- Juge : `mistral-large-latest` + embeddings `mistral-embed`, ragas 0.4.3
- Questions sans contexte (aucun outil appelé ou erreur API) : 2
- Questions sans aucun score (échec du juge) : 0
- Choix d'outils conforme (outils nécessaires appelés) : 22 / 22
- Intégrité de la base après l'évaluation : intacte ({'teams': 30, 'players': 569, 'stats': 569, 'report_messages': 355, 'checksum_stats': 480222})

## Scores moyens par catégorie

| catégorie | n | faithfulness | answer_relevancy | llm_context_precision_with_reference | context_recall | factual_correctness | exactitude_reponse | refus_sans_invention | refus_modification |
|---|---|---|---|---|---|---|---|---|---|
| mixte | 8 | 0.88 | 0.68 | 0.49 | 0.96 | 0.46 | 0.75 | — | — |
| arbitrage | 4 | 0.82 | 0.46 | 0.19 | 0.75 | 0.34 | 0.50 | — | — |
| piege_unite | 4 | 0.94 | 0.97 | 1.00 | 0.75 | 0.64 | 1.00 | — | — |
| homonyme | 3 | 0.67 | 0.90 | 0.94 | 0.56 | 0.46 | 0.67 | — | — |
| seuil_implicite | 3 | 0.97 | 0.97 | 1.00 | 0.61 | 0.38 | 0.33 | — | — |
| hors_couverture | 3 | — | — | — | — | 0.45 | — | 1.00 | — |
| injection | 3 | — | — | — | — | — | — | — | 1.00 |
| **global** | 28 | 0.86 | 0.76 | 0.66 | 0.78 | 0.46 | 0.68 | 1.00 | 1.00 |

`—` : métrique non applicable. Les métriques de contexte et de pertinence ne sont pas calculées sur `hors_couverture` (aucun contexte pertinent par construction, et un refus correct est noté 0 par answer_relevancy) ; `refus_sans_invention` n'est calculée que sur cette catégorie, et `refus_modification` (refus de modifier les données) que sur `injection`.
