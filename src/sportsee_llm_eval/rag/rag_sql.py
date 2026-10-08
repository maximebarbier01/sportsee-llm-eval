"""Agent rag_sql : le LLM choisit entre la recherche documentaire et l'outil SQL.

Extension de rag_v2 (même modèle mistral-small, même sortie structurée RagResponse, même
validation des sources), avec deux outils appelés à la demande par l'agent Pydantic AI :
- rechercher_documents : recherche vectorielle de rag_v2 (fiches, définitions, Reddit) ;
- interroger_base_statistiques : l'outil LangChain SQL (sql_tool.py), pour les questions
  chiffrées (valeurs, classements, totaux, moyennes, comparaisons, filtres).

Chaque résultat d'outil reçoit un identifiant (doc_id des documents, « sql::N » pour une
requête) que la réponse doit citer : le validateur refuse une réponse dont les sources ne
proviennent pas d'un appel d'outil, et relance l'agent.
"""

from dataclasses import dataclass, field

import logfire
from langchain_core.tools import BaseTool
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.mistral import MistralModel

from sportsee_llm_eval.observability.logfire_setup import setup_logfire
from sportsee_llm_eval.rag.rag_v2 import MODEL_NAME, RagResponse, RagV2, format_context
from sportsee_llm_eval.sql.sql_tool import SqlTool

INSTRUCTIONS = """\
Tu es l'assistant d'analyse de performance de SportSee. Tu réponds à des entraîneurs, \
analystes et préparateurs physiques d'un club de basketball.

Tu disposes de deux outils :
- interroger_base_statistiques : base des statistiques de saison régulière des 569 joueurs \
et 30 équipes. Utilise-le pour toute question chiffrée : la valeur d'un joueur, un \
classement (« le meilleur », « le plus de »), un total ou une moyenne par équipe, une \
comparaison, un filtre (âge, nombre de matchs, de tentatives...). Passe-lui la question \
chiffrée reformulée de façon claire et complète.
- rechercher_documents : discussions Reddit r/nba (avis de fans, débats, tableaux cités par \
les fans) et définitions des statistiques. Utilise-le pour les opinions, ce que disent les \
fans, et la signification d'une statistique.
Pour une question qui mêle les deux (par exemple les statistiques d'un joueur cité sur \
Reddit), appelle les deux outils.

Règles :
1. Réponds UNIQUEMENT à partir des résultats des outils. N'utilise jamais tes connaissances \
générales sur la NBA, même si tu penses les connaître.
2. Si les outils ne permettent pas de répondre (aucune ligne, 'donnees_indisponibles', \
aucun document pertinent), mets information_disponible à false, dis quelle information \
manque, et ne donne AUCUN chiffre, nom ou classement de remplacement. Les données ne \
contiennent ni statistiques par match, ni domicile / extérieur, ni salaires.
3. Les statistiques sont des totaux de saison régulière (sauf minutes et plus-minus, qui \
sont des moyennes par match). N'attribue pas d'année de saison absente des données.
4. Réponds en français, de façon concise et factuelle : la réponse d'abord, avec les \
valeurs exactes renvoyées par les outils.
5. Présente les opinions Reddit comme des avis de fans.
6. Dans sources, liste les identifiants [entre crochets] des résultats d'outils utilisés.
"""


@dataclass
class RagSqlDeps:
    rag: RagV2
    sql_tool: BaseTool
    seen_ids: set[str] = field(default_factory=set)
    contexts: list[str] = field(default_factory=list)  # pour l'évaluation RAGAS
    tools_called: list[str] = field(default_factory=list)


def build_agent(model_name: str = MODEL_NAME) -> Agent[RagSqlDeps, RagResponse]:
    agent = Agent(
        MistralModel(model_name),
        output_type=RagResponse,
        deps_type=RagSqlDeps,
        instructions=INSTRUCTIONS,
        model_settings={"temperature": 0.0},
        retries=2,
        name="rag_sql",
    )

    @agent.tool
    def rechercher_documents(ctx: RunContext[RagSqlDeps], requete: str) -> str:
        """Recherche dans les discussions Reddit et les définitions des statistiques."""
        documents = ctx.deps.rag.retrieve(requete)
        ctx.deps.tools_called.append("rechercher_documents")
        ctx.deps.seen_ids.update(d.id for d in documents)
        ctx.deps.contexts += [d.page_content for d in documents]
        return format_context(documents) or "Aucun document trouvé."

    @agent.tool
    def interroger_base_statistiques(ctx: RunContext[RagSqlDeps], question: str) -> str:
        """Interroge la base des statistiques de saison (joueurs, équipes) avec une requête
        SQL générée à partir de la question chiffrée."""
        ctx.deps.tools_called.append("interroger_base_statistiques")
        result_id = f"sql::{sum(i.startswith('sql::') for i in ctx.deps.seen_ids) + 1}"
        text = ctx.deps.sql_tool.invoke({"question": question})  # outil LangChain
        ctx.deps.seen_ids.add(result_id)
        ctx.deps.contexts.append(text)
        return f"[{result_id}]\n{text}"

    @agent.output_validator
    def sources_des_outils(
        ctx: RunContext[RagSqlDeps], output: RagResponse
    ) -> RagResponse:
        unknown = [s for s in output.sources if s not in ctx.deps.seen_ids]
        if unknown:
            raise ModelRetry(
                f"Sources inconnues {unknown} : cite uniquement des identifiants renvoyés "
                f"par les outils ({sorted(ctx.deps.seen_ids)})."
            )
        if output.information_disponible and not output.sources:
            raise ModelRetry(
                "Appelle un outil et cite ses résultats, ou déclare l'information indisponible."
            )
        return output

    return agent


class RagSql:
    def __init__(self, model_name: str = MODEL_NAME) -> None:
        setup_logfire()
        self.model_name = model_name
        self.rag = RagV2(model_name=model_name)
        self.sql = SqlTool(model_name=model_name)
        self.sql_tool = self.sql.as_langchain_tool()
        self.agent = build_agent(model_name)

    def ask(self, question: str) -> tuple[RagResponse, RagSqlDeps]:
        deps = RagSqlDeps(rag=self.rag, sql_tool=self.sql_tool)
        with logfire.span("rag_sql", question=question) as span:
            result = self.agent.run_sync(question, deps=deps)
            span.set_attribute("outils_appeles", deps.tools_called)
        return result.output, deps
