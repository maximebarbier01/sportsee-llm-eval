# Évaluation RAGAS : rag_sql

- Date : 2026-10-09T10:00:25+02:00
- Questions : 32 (evaluation/questions/questions_v1.json)
- Système : modèle `mistral-small-latest`, température 0.0, k=5
- Juge : `mistral-large-latest` + embeddings `mistral-embed`, ragas 0.4.3
- Questions sans contexte (aucun outil appelé ou erreur API) : 1
- Questions sans aucun score (échec du juge) : 0
- Intégrité de la base après l'évaluation : intacte ({'teams': 30, 'players': 569, 'stats': 569, 'report_messages': 355, 'checksum_stats': 480222})

## Scores moyens par catégorie

| catégorie | n | faithfulness | answer_relevancy | llm_context_precision_with_reference | context_recall | factual_correctness | exactitude_reponse | refus_sans_invention | refus_modification |
|---|---|---|---|---|---|---|---|---|---|
| simple | 7 | 1.00 | 0.92 | 1.00 | 0.86 | 0.76 | 1.00 | — | — |
| complexe | 7 | 0.92 | 0.95 | 0.95 | 0.81 | 0.55 | 0.86 | — | — |
| bruitee | 5 | 1.00 | 0.82 | 0.89 | 1.00 | 0.57 | 1.00 | — | — |
| texte | 6 | 0.72 | 0.79 | 0.80 | 0.94 | 0.21 | 0.80 | — | — |
| mixte | 3 | 0.86 | 0.87 | 0.52 | 1.00 | 0.56 | 1.00 | — | — |
| hors_couverture | 4 | — | — | — | — | 0.39 | — | 0.75 | — |
| **global** | 32 | 0.91 | 0.87 | 0.87 | 0.90 | 0.52 | 0.93 | 0.75 | — |

`—` : métrique non applicable. Les métriques de contexte et de pertinence ne sont pas calculées sur `hors_couverture` (aucun contexte pertinent par construction, et un refus correct est noté 0 par answer_relevancy) ; `refus_sans_invention` n'est calculée que sur cette catégorie, et `refus_modification` (refus de modifier les données) que sur `injection`.
