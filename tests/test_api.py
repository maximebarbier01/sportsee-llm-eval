"""Tests de l'API REST, avec un faux assistant (aucun appel à l'API Mistral)."""

from dataclasses import dataclass, field

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelHTTPError

from sportsee_llm_eval.api.main import API_VERSION, app, get_assistant_loader
from sportsee_llm_eval.rag.rag_v2 import RagResponse


@dataclass
class FakeDeps:
    tools_called: list[str] = field(
        default_factory=lambda: ["interroger_base_statistiques"]
    )


class FakeAssistant:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def ask(self, question: str):
        self.questions.append(question)
        response = RagResponse(
            reponse="Dyson Daniels, avec 228 interceptions.",
            information_disponible=True,
            sources=["sql::1"],
        )
        return response, FakeDeps()


@pytest.fixture
def client():
    fake = FakeAssistant()
    loaded: list[str] = []

    def loader(system):
        loaded.append(system)
        return fake

    app.dependency_overrides[get_assistant_loader] = lambda: loader
    with TestClient(app) as c:
        c.fake, c.loaded = fake, loaded
        yield c
    app.dependency_overrides.clear()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == API_VERSION
    assert body["status"] in {"ok", "degraded"}
    assert set(body) == {
        "status",
        "version",
        "base_sqlite",
        "index_vectoriel",
        "cle_mistral",
    }


def test_ask_renvoie_une_reponse_structuree(client):
    r = client.post(
        "/ask", json={"question": "Quel joueur a le plus d'interceptions ?"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reponse"].startswith("Dyson Daniels")
    assert body["information_disponible"] is True
    assert body["sources"] == ["sql::1"]
    assert body["outils_appeles"] == ["interroger_base_statistiques"]
    assert body["systeme"] == "rag_sql"  # système par défaut
    assert body["latence_s"] >= 0
    assert client.fake.questions == ["Quel joueur a le plus d'interceptions ?"]


def test_ask_choix_du_systeme(client):
    r = client.post(
        "/ask", json={"question": "Que mesure le PIE ?", "system": "rag_v2"}
    )
    assert r.status_code == 200
    assert r.json()["systeme"] == "rag_v2"
    assert client.loaded == ["rag_v2"]


@pytest.mark.parametrize(
    "payload",
    [
        {"question": ""},
        {"question": "ab"},
        {"question": "x" * 501},
        {"question": "Que mesure le PIE ?", "system": "prototype"},
        {},
    ],
)
def test_ask_requete_invalide(client, payload):
    assert client.post("/ask", json=payload).status_code == 422
    assert client.fake.questions == []  # l'assistant n'est jamais appelé


def test_ask_assistant_indisponible():
    def failing_loader(system):
        raise FileNotFoundError("Base absente : data/database/sportsee.db")

    app.dependency_overrides[get_assistant_loader] = lambda: failing_loader
    try:
        with TestClient(app) as c:
            r = c.post("/ask", json={"question": "Quel joueur a le plus de points ?"})
        assert r.status_code == 503
        assert "Base absente" in r.json()["detail"]
    finally:
        app.dependency_overrides.clear()


class FailingAssistant:
    """Assistant dont l'appel à Mistral échoue (panne côté fournisseur)."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def ask(self, question: str):
        raise self.error


@pytest.mark.parametrize(
    "error, code",
    [
        (
            ModelHTTPError(503, "mistral-small-latest", body="Service unavailable."),
            "503",
        ),
        (
            httpx.HTTPStatusError(
                "503",
                request=httpx.Request(
                    "POST", "https://api.mistral.ai/v1/chat/completions"
                ),
                response=httpx.Response(503),
            ),
            "503",
        ),
        (httpx.ConnectError("connexion refusée"), "réseau"),
    ],
)
def test_ask_panne_mistral(error, code):
    app.dependency_overrides[get_assistant_loader] = lambda: (
        lambda system: FailingAssistant(error)
    )
    try:
        with TestClient(app) as c:
            r = c.post("/ask", json={"question": "Quel joueur a le plus de points ?"})
        assert r.status_code == 503
        assert "Service Mistral" in r.json()["detail"]
        assert f"code {code}" in r.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_documentation_openapi(client):
    schema = client.get("/openapi.json").json()
    assert {"/ask", "/health"} <= set(schema["paths"])
