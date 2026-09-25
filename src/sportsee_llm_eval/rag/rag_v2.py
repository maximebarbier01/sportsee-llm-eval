"""Chaîne RAG v2 : recherche dans l'index rag_v2 puis réponse structurée via Pydantic AI.

Différences avec le prototype :
- index construit par le pipeline de préparation (fiches joueur / équipe / dictionnaire,
  threads Reddit nettoyés), au lieu de blocs de tableau sans en-têtes ;
- prompt destiné aux coachs et analystes, qui impose de répondre uniquement à partir du
  contexte et de déclarer l'information indisponible plutôt que de l'inventer ;
- sortie structurée et validée (RagResponse) : réponse, disponibilité de l'information et
  sources citées. Un validateur vérifie que les sources citées font bien partie du contexte
  fourni ; sinon l'agent est relancé (ModelRetry).

Mêmes modèle et nombre d'extraits que le prototype (mistral-small-latest, k=5), pour que la
comparaison mesure l'effet des données et du prompt. Seul ajout : quand un extrait d'un
thread Reddit est retrouvé, le post initial du thread est joint au contexte (les dizaines de
commentaires d'un même thread éclipsent sinon le post, qui porte le sujet de la discussion).
"""

from dataclasses import dataclass

import logfire
from langchain_core.documents import Document
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.mistral import MistralModel

from sportsee_llm_eval.observability.logfire_setup import setup_logfire
from sportsee_llm_eval.preparation.build_index import load_index

MODEL_NAME = "mistral-small-latest"
TOP_K = 5

INSTRUCTIONS = """\
Tu es l'assistant d'analyse de performance de SportSee. Tu réponds à des entraîneurs, \
analystes et préparateurs physiques d'un club de basketball.

Règles :
1. Réponds UNIQUEMENT à partir des documents du contexte. N'utilise jamais tes connaissances \
générales sur la NBA, même si tu penses les connaître.
2. Si le contexte ne permet pas de répondre, mets information_disponible à false et dis \
clairement quelle information manque. Ne donne alors AUCUN chiffre, nom ou classement de \
remplacement.
3. Les statistiques sont celles de la saison régulière contenue dans les données. Les \
statistiques de comptage (points, rebonds, passes...) sont des totaux sur la saison. \
N'attribue pas d'année de saison qui ne figure pas dans le contexte.
4. Réponds en français, de façon concise et factuelle : la réponse d'abord, avec les \
valeurs chiffrées exactes du contexte, puis au besoin une phrase de précision.
5. Les opinions tirées de Reddit sont des avis de fans : présente-les comme tels.
6. Dans sources, liste les identifiants [entre crochets] des documents que tu as utilisés.
7. Le contexte ne contient que quelques fiches joueur : n'en déduis jamais un classement ou \
un maximum sur toute la ligue (« le meilleur », « le plus de »). Ne réponds à ce type de \
question que si un document du contexte donne explicitement ce classement (par exemple une \
fiche équipe pour une question sur une équipe) ; sinon, déclare l'information indisponible.
"""


class RagResponse(BaseModel):
    """Sortie structurée de l'assistant, validée avant d'être renvoyée."""

    reponse: str = Field(
        min_length=1, description="Réponse en français, fondée sur le contexte"
    )
    information_disponible: bool = Field(
        description="false si le contexte ne permet pas de répondre à la question"
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Identifiants des documents du contexte utilisés pour répondre",
    )


@dataclass
class RagDeps:
    """Dépendances d'une exécution : les identifiants des documents fournis en contexte."""

    context_ids: set[str]


def build_agent(model_name: str = MODEL_NAME) -> Agent[RagDeps, RagResponse]:
    agent = Agent(
        MistralModel(model_name),
        output_type=RagResponse,
        deps_type=RagDeps,
        instructions=INSTRUCTIONS,
        model_settings={"temperature": 0.0},
        retries=2,
        name="rag_v2",
    )

    @agent.output_validator
    def sources_du_contexte(
        ctx: RunContext[RagDeps], output: RagResponse
    ) -> RagResponse:
        unknown = [s for s in output.sources if s not in ctx.deps.context_ids]
        if unknown:
            raise ModelRetry(
                f"Sources inconnues {unknown} : cite uniquement des identifiants du contexte "
                f"({sorted(ctx.deps.context_ids)})."
            )
        if output.information_disponible and not output.sources:
            raise ModelRetry(
                "Cite au moins une source du contexte, ou déclare l'information indisponible."
            )
        return output

    return agent


def format_context(documents: list[Document]) -> str:
    return "\n\n".join(
        f"[{d.id}] (source : {d.metadata.get('source', 'inconnue')})\n{d.page_content}"
        for d in documents
    )


class RagV2:
    def __init__(self, k: int = TOP_K, model_name: str = MODEL_NAME) -> None:
        setup_logfire()
        self.k = k
        self.model_name = model_name
        self.store = load_index()
        self.agent = build_agent(model_name)
        self.n_players = sum(
            d.metadata.get("source_type") == "joueur"
            for d in self.store.docstore._dict.values()
        )
        self.thread_posts: dict[str, list[Document]] = {}
        for doc in self.store.docstore._dict.values():
            if doc.metadata.get("is_thread_post"):
                self.thread_posts.setdefault(doc.metadata["thread_title"], []).append(
                    doc
                )
        for posts in self.thread_posts.values():
            posts.sort(key=lambda d: d.id)

    def retrieve(self, question: str) -> list[Document]:
        with logfire.span("recherche vectorielle", question=question, k=self.k) as span:
            results = self.store.similarity_search_with_score(question, k=self.k)
            documents = [d for d, _ in results]
            # post initial des threads Reddit retrouvés, s'il n'est pas déjà dans les résultats
            seen = {d.id for d in documents}
            for title in dict.fromkeys(
                d.metadata.get("thread_title") for d in documents
            ):
                for post in self.thread_posts.get(title, []) if title else []:
                    if post.id not in seen:
                        documents.append(post)
                        seen.add(post.id)
            span.set_attribute(
                "documents",
                [{"id": d.id, "score": round(float(s), 3)} for d, s in results],
            )
            span.set_attribute(
                "posts_ajoutes", [d.id for d in documents[len(results) :]]
            )
        return documents

    def ask(self, question: str) -> tuple[RagResponse, list[Document]]:
        with logfire.span("rag_v2", question=question):
            documents = self.retrieve(question)
            prompt = f"Contexte :\n{format_context(documents)}\n\n"
            n_players = sum(
                d.metadata.get("source_type") == "joueur" for d in documents
            )
            if n_players:
                # rappel concret de la règle 7, placé au plus près de la question
                prompt += (
                    f"Attention : ce contexte ne contient que {n_players} fiche(s) joueur sur "
                    f"les {self.n_players} joueurs de la saison. Il ne permet pas de dire quel "
                    "joueur est le premier ou le meilleur de toute la ligue.\n\n"
                )
            prompt += f"Question : {question}"
            result = self.agent.run_sync(
                prompt, deps=RagDeps(context_ids={d.id for d in documents})
            )
            return result.output, documents
