import json
import logging

from langchain_core.messages import AIMessage, HumanMessage

from db.redis_client import redis

logger = logging.getLogger(__name__)


def _deserialize_messages(items):
    messages = []
    for item in items:
        message_type = HumanMessage if item["role"] == "user" else AIMessage
        messages.append(message_type(content=item["content"]))
    return messages


def load_memory(state):
    user_id = state["user_id"]
    data = redis.get(user_id)

    if not data:
        return {"messages": [], "pending_messages": [], "summary": ""}

    data = json.loads(data)
    messages = _deserialize_messages(data.get("messages", []))
    # 旧版 Redis 数据没有 pending_messages，按空列表读取即可平滑升级。
    pending_messages = _deserialize_messages(data.get("pending_messages", []))

    # 日志中的 %s 会替换为 user_id，%d 会替换为消息数量；logger 会在输出时完成格式化。
    logger.info("Loaded memory for user %s (%d messages)", user_id, len(messages))
    return {
        "messages": messages,
        "pending_messages": pending_messages,
        "summary": data.get("summary", ""),
    }
