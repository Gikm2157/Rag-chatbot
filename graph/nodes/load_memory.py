import json
import logging

from langchain_core.messages import AIMessage, HumanMessage

from db.redis_client import redis

logger = logging.getLogger(__name__)


def load_memory(state):
    user_id = state["user_id"]
    data = redis.get(user_id)

    if not data:
        return {"messages": [], "summary": ""}

    data = json.loads(data)
    messages = []
    for m in data.get("messages", []):
        if m["role"] == "user":
            messages.append(HumanMessage(content=m["content"]))
        else:
            messages.append(AIMessage(content=m["content"]))

    # 日志中的 %s 会替换为 user_id，%d 会替换为消息数量；logger 会在输出时完成格式化。
    logger.info("Loaded memory for user %s (%d messages)", user_id, len(messages))
    return {"messages": messages, "summary": data.get("summary", "")}
