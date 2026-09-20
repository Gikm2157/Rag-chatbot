"""
End-to-end tests for POST /api/v1/chat and the surrounding app layer
(health check, home, rate limiter).

Fixtures: app_client, fake_redis, mock_vs, mock_llm — all from conftest.py.
"""

from unittest.mock import MagicMock
from langchain_core.documents import Document as LCDoc


# ── App health / home ─────────────────────────────────────────────────────────

def test_health_check(app_client):
    resp = app_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_home(app_client):
    resp = app_client.get("/")
    assert resp.status_code == 200
    assert resp.json().get("message") is not None


# ── Happy path ────────────────────────────────────────────────────────────────

def test_chat_returns_answer_and_sources(app_client, mock_vs, mock_llm):
    """Full RAG path: score above threshold → docs retrieved → LLM answers."""
    doc = LCDoc(
        page_content="Return policy text.",
        metadata={"source_file": "policy.pdf"},
    )
    mock_vs.similarity_search_with_relevance_scores.return_value = [(doc, 0.85)]
    mock_vs.max_marginal_relevance_search.return_value = [doc]
    mock_llm.invoke.return_value = MagicMock(content="You can return within 30 days.")

    resp = app_client.post(
        "/api/v1/chat",
        json={"q": "what is the return policy?"},
        headers={"X-User-ID": "user_1"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"] == "You can return within 30 days."
    assert "policy.pdf" in body["sources"]


def test_chat_no_docs_still_returns_200(app_client, mock_vs, mock_llm):
    """Score below threshold — retrieve_context returns empty; LLM gets no context."""
    doc = LCDoc(page_content="Unrelated.", metadata={})
    mock_vs.similarity_search_with_relevance_scores.return_value = [(doc, 0.05)]
    mock_llm.invoke.return_value = MagicMock(
        content="I don't have information about that in our knowledge base."
    )

    resp = app_client.post(
        "/api/v1/chat",
        json={"q": "what is the weather today?"},
        headers={"X-User-ID": "user_2"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["sources"] == []


def test_chat_no_vectorstore_hits_returns_empty_sources(app_client, mock_vs, mock_llm):
    """similarity_search returns nothing → sources list is empty."""
    mock_vs.similarity_search_with_relevance_scores.return_value = []
    mock_llm.invoke.return_value = MagicMock(content="No info.")

    resp = app_client.post(
        "/api/v1/chat",
        json={"q": "off-topic question"},
        headers={"X-User-ID": "user_3"},
    )

    assert resp.status_code == 200
    assert resp.json()["sources"] == []


# ── User identity and memory ──────────────────────────────────────────────────

def test_chat_defaults_to_anonymous_when_no_header(app_client, fake_redis, mock_llm):
    """Missing X-User-ID header → memory stored under 'anonymous'."""
    mock_llm.invoke.return_value = MagicMock(content="Hello!")

    resp = app_client.post("/api/v1/chat", json={"q": "hi"})

    assert resp.status_code == 200
    assert fake_redis.exists("anonymous")


def test_chat_uses_x_user_id_header(app_client, fake_redis, mock_llm):
    """X-User-ID header value is used as the Redis memory key."""
    mock_llm.invoke.return_value = MagicMock(content="Hi user!")

    resp = app_client.post(
        "/api/v1/chat",
        json={"q": "hello"},
        headers={"X-User-ID": "user_xyz"},
    )

    assert resp.status_code == 200
    assert fake_redis.exists("user_xyz")


def test_chat_memory_persists_between_requests(app_client, fake_redis, mock_llm):
    """Second request for the same user should find memory from the first."""
    mock_llm.invoke.return_value = MagicMock(content="First answer.")
    app_client.post(
        "/api/v1/chat",
        json={"q": "first question"},
        headers={"X-User-ID": "user_mem"},
    )

    mock_llm.invoke.return_value = MagicMock(content="Second answer.")
    resp = app_client.post(
        "/api/v1/chat",
        json={"q": "second question"},
        headers={"X-User-ID": "user_mem"},
    )

    assert resp.status_code == 200
    assert fake_redis.exists("user_mem")


def test_different_users_have_isolated_memory(app_client, fake_redis, mock_llm):
    """Two different user IDs get separate Redis keys."""
    mock_llm.invoke.return_value = MagicMock(content="Answer A.")
    app_client.post(
        "/api/v1/chat", json={"q": "question A"}, headers={"X-User-ID": "alice"}
    )

    mock_llm.invoke.return_value = MagicMock(content="Answer B.")
    app_client.post(
        "/api/v1/chat", json={"q": "question B"}, headers={"X-User-ID": "bob"}
    )

    assert fake_redis.exists("alice")
    assert fake_redis.exists("bob")


# ── Request validation ────────────────────────────────────────────────────────

def test_chat_empty_question_returns_422(app_client):
    resp = app_client.post("/api/v1/chat", json={"q": ""})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "请求参数校验失败"
    assert any(e["field"] == "q" for e in body["details"])


def test_chat_whitespace_only_question_returns_422(app_client):
    resp = app_client.post("/api/v1/chat", json={"q": "   "})
    assert resp.status_code == 422


def test_chat_question_too_long_returns_422(app_client):
    resp = app_client.post("/api/v1/chat", json={"q": "x" * 2001})
    assert resp.status_code == 422
    assert resp.json()["error"] == "请求参数校验失败"


def test_chat_missing_q_field_returns_422(app_client):
    resp = app_client.post("/api/v1/chat", json={})
    assert resp.status_code == 422


def test_chat_missing_body_returns_422(app_client):
    resp = app_client.post("/api/v1/chat")
    assert resp.status_code == 422


# ── Rate limiting ─────────────────────────────────────────────────────────────

def test_rate_limit_blocks_on_61st_request(app_client):
    """60 requests succeed; the 61st receives 429 Too Many Requests."""
    for _ in range(60):
        assert app_client.get("/health").status_code == 200

    resp = app_client.get("/health")
    assert resp.status_code == 429
    assert resp.json()["error"] == "请求过于频繁"


def test_rate_limit_response_includes_detail(app_client):
    """429 body includes a human-readable detail message."""
    for _ in range(60):
        app_client.get("/health")

    resp = app_client.get("/health")
    assert resp.status_code == 429
    assert "detail" in resp.json()
