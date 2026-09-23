"""
POST /api/v1/chat 及其外围应用层（健康检查、首页、限流器）的端到端测试。

app_client、fake_redis、mock_vs、mock_llm 夹具均来自 conftest.py。
"""

import json
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.documents import Document as LCDoc


def _serialized_turns(count: int, prefix: str = "历史") -> list[dict[str, str]]:
    """生成指定轮数的 Redis 消息，便于测试记忆窗口和摘要边界。"""
    messages = []
    for index in range(count):
        messages.extend(
            [
                {"role": "user", "content": f"{prefix}问题{index + 1}"},
                {"role": "ai", "content": f"{prefix}回答{index + 1}"},
            ]
        )
    return messages


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
    # 旧数据没有 pending_messages 时按空列表读取，本轮不会过早触发摘要。
    assert mock_llm.invoke.call_count == 1
    sent_messages = mock_llm.invoke.call_args_list[0].args[0]
    assert isinstance(sent_messages[0], SystemMessage)
    assert "企业知识库客服助手" in sent_messages[0].content
    assert isinstance(sent_messages[1], HumanMessage)
    assert sent_messages[1].content == "怎么申请退款？"
    assert isinstance(sent_messages[2], AIMessage)
    assert sent_messages[2].content == "请在订单详情页提交申请。"
    assert isinstance(sent_messages[-1], HumanMessage)
    assert "入口在哪里？" in sent_messages[-1].content

    stored = json.loads(fake_redis.get("system-message-user"))
    assert len(stored["pending_messages"]) == 2


def test_chat_keeps_only_the_latest_five_turns(app_client, fake_redis, mock_llm):
    """短期记忆只保存最近 10 条消息，但待摘要消息仍独立累计。"""
    fake_redis.set(
        "recent-window-user",
        json.dumps(
            {
                "summary": "",
                "messages": _serialized_turns(5),
                "pending_messages": [],
            }
        ),
    )
    mock_llm.invoke.return_value = MagicMock(content="当前回答")

    response = app_client.post(
        "/api/v1/chat",
        headers={"x-user-id": "recent-window-user"},
        json={"q": "当前问题"},
    )

    assert response.status_code == 200
    stored = json.loads(fake_redis.get("recent-window-user"))
    assert len(stored["messages"]) == 10
    assert stored["messages"][-2:] == [
        {"role": "user", "content": "当前问题"},
        {"role": "ai", "content": "当前回答"},
    ]
    assert stored["pending_messages"] == stored["messages"][-2:]


def test_chat_does_not_summarize_before_twenty_pending_messages(
    app_client, fake_redis, mock_llm
):
    """18 条待摘要消息仍低于 20 条边界，不应额外调用摘要模型。"""
    fake_redis.set(
        "below-summary-threshold-user",
        json.dumps(
            {
                "summary": "旧摘要",
                "messages": _serialized_turns(5),
                "pending_messages": _serialized_turns(8),
            }
        ),
    )
    mock_llm.invoke.return_value = MagicMock(content="当前回答")

    response = app_client.post(
        "/api/v1/chat",
        headers={"x-user-id": "below-summary-threshold-user"},
        json={"q": "当前问题"},
    )

    assert response.status_code == 200
    assert mock_llm.invoke.call_count == 1
    stored = json.loads(fake_redis.get("below-summary-threshold-user"))
    assert stored["summary"] == "旧摘要"
    assert len(stored["pending_messages"]) == 18


def test_chat_updates_rolling_summary_at_twenty_pending_messages(
    app_client, fake_redis, mock_llm
):
    """待摘要消息达到 20 条时，合并旧摘要并在成功后清空待摘要消息。"""
    fake_redis.set(
        "rolling-summary-user",
        json.dumps(
            {
                "summary": "用户此前咨询退款条件。",
                "messages": _serialized_turns(5),
                "pending_messages": _serialized_turns(9),
            }
        ),
    )
    mock_llm.invoke.side_effect = [
        MagicMock(content="当前回答"),
        MagicMock(content="更新后的长期摘要"),
    ]

    response = app_client.post(
        "/api/v1/chat",
        headers={"x-user-id": "rolling-summary-user"},
        json={"q": "退款多久能到账？"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == "当前回答"
    assert mock_llm.invoke.call_count == 2
    summary_prompt = mock_llm.invoke.call_args_list[1].args[0]
    assert "用户此前咨询退款条件。" in summary_prompt
    assert "退款多久能到账？" in summary_prompt
    assert "当前回答" in summary_prompt

    stored = json.loads(fake_redis.get("rolling-summary-user"))
    assert stored["summary"] == "更新后的长期摘要"
    assert stored["pending_messages"] == []
    assert len(stored["messages"]) == 10


def test_summary_failure_keeps_previous_redis_memory(
    app_client, fake_redis, mock_llm
):
    """摘要模型失败时 store_memory 不执行，不能覆盖上一次成功保存的记忆。"""
    original = {
        "summary": "原有摘要",
        "messages": _serialized_turns(5),
        "pending_messages": _serialized_turns(9),
    }
    fake_redis.set("summary-failure-user", json.dumps(original))
    mock_llm.invoke.side_effect = [
        MagicMock(content="本轮回答"),
        RuntimeError("summary unavailable"),
    ]

    response = app_client.post(
        "/api/v1/chat",
        headers={"x-user-id": "summary-failure-user"},
        json={"q": "本轮问题"},
    )

    assert response.status_code == 500
    assert json.loads(fake_redis.get("summary-failure-user")) == original


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
