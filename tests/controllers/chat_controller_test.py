"""
POST /api/v1/chat 及其外围应用层（健康检查、首页、限流器）的端到端测试。

app_client、fake_redis、mock_vs、mock_llm 夹具均来自 conftest.py。
"""

import json
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.documents import Document as LCDoc


# ── 应用健康检查与首页 ───────────────────────────────────────────────────────

def test_health_check(app_client):
    resp = app_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_home(app_client):
    resp = app_client.get("/")
    assert resp.status_code == 200
    assert resp.json().get("message") is not None


# ── 正常流程 ─────────────────────────────────────────────────────────────────

def test_chat_returns_answer_and_sources(app_client, mock_vs, mock_llm):
    """完整 RAG 流程：分数超过阈值 → 检索文档 → 大模型回答。"""
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


def test_chat_sends_system_message_and_preserves_recent_roles(
    app_client, fake_redis, mock_llm
):
    """回答模型应收到 SystemMessage，并保留历史消息的真实角色。"""
    fake_redis.set(
        "system-message-user",
        json.dumps(
            {
                "summary": "用户正在咨询退款。",
                "messages": [
                    {"role": "user", "content": "怎么申请退款？"},
                    {"role": "ai", "content": "请在订单详情页提交申请。"},
                ],
            }
        ),
    )
    mock_llm.invoke.return_value = MagicMock(content="可以在订单详情页申请退款。")

    response = app_client.post(
        "/api/v1/chat",
        headers={"x-user-id": "system-message-user"},
        json={"q": "入口在哪里？"},
    )

    assert response.status_code == 200
    # 第一次调用用于生成回答；达到摘要阈值后，第二次调用才用于生成摘要。
    sent_messages = mock_llm.invoke.call_args_list[0].args[0]
    assert isinstance(sent_messages[0], SystemMessage)
    assert "企业知识库客服助手" in sent_messages[0].content
    assert isinstance(sent_messages[1], HumanMessage)
    assert sent_messages[1].content == "怎么申请退款？"
    assert isinstance(sent_messages[2], AIMessage)
    assert sent_messages[2].content == "请在订单详情页提交申请。"
    assert isinstance(sent_messages[-1], HumanMessage)
    assert "入口在哪里？" in sent_messages[-1].content


def test_chat_no_docs_still_returns_200(app_client, mock_vs, mock_llm):
    """分数低于阈值时 retrieve_context 返回空结果，大模型收不到文档上下文。"""
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
    """相似度检索没有结果时，来源列表为空。"""
    mock_vs.similarity_search_with_relevance_scores.return_value = []
    mock_llm.invoke.return_value = MagicMock(content="No info.")

    resp = app_client.post(
        "/api/v1/chat",
        json={"q": "off-topic question"},
        headers={"X-User-ID": "user_3"},
    )

    assert resp.status_code == 200
    assert resp.json()["sources"] == []


# ── 用户身份与对话记忆 ───────────────────────────────────────────────────────

def test_chat_defaults_to_anonymous_when_no_header(app_client, fake_redis, mock_llm):
    """缺少 X-User-ID 请求头时，使用 anonymous 保存对话记忆。"""
    mock_llm.invoke.return_value = MagicMock(content="Hello!")

    resp = app_client.post("/api/v1/chat", json={"q": "hi"})

    assert resp.status_code == 200
    assert fake_redis.exists("anonymous")


def test_chat_uses_x_user_id_header(app_client, fake_redis, mock_llm):
    """使用 X-User-ID 请求头的值作为 Redis 记忆键。"""
    mock_llm.invoke.return_value = MagicMock(content="Hi user!")

    resp = app_client.post(
        "/api/v1/chat",
        json={"q": "hello"},
        headers={"X-User-ID": "user_xyz"},
    )

    assert resp.status_code == 200
    assert fake_redis.exists("user_xyz")


def test_chat_memory_persists_between_requests(app_client, fake_redis, mock_llm):
    """同一用户的第二次请求应该能够读取第一次请求留下的记忆。"""
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
    """两个不同用户 ID 应使用各自独立的 Redis 键。"""
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


# ── 请求参数校验 ─────────────────────────────────────────────────────────────

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


# ── 请求限流 ─────────────────────────────────────────────────────────────────

def test_rate_limit_blocks_on_61st_request(app_client):
    """前 60 次请求成功，第 61 次收到 429 请求过多。"""
    for _ in range(60):
        assert app_client.get("/health").status_code == 200

    resp = app_client.get("/health")
    assert resp.status_code == 429
    assert resp.json()["error"] == "请求过于频繁"


def test_rate_limit_response_includes_detail(app_client):
    """429 响应体包含便于理解的详细说明。"""
    for _ in range(60):
        app_client.get("/health")

    resp = app_client.get("/health")
    assert resp.status_code == 429
    assert "detail" in resp.json()
