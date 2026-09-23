import json
import logging

from langchain_core.messages import AIMessage, HumanMessage

from config import get_settings
from db.redis_client import redis

logger = logging.getLogger(__name__)


def _serialize_messages(messages):
    serialized = []
    for m in messages:
        if isinstance(m, HumanMessage):
            serialized.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage):
            serialized.append({"role": "ai", "content": m.content})
    return serialized


def store_memory(state):
    messages = state.get("messages") or []
    pending_messages = state.get("pending_messages") or []

    data = {
        "summary": state.get("summary", ""),
        "messages": _serialize_messages(messages),
        "pending_messages": _serialize_messages(pending_messages),
    }

    ttl = get_settings().redis_ttl_seconds
    redis.set(state["user_id"], json.dumps(data), ex=ttl)
    logger.info("Stored memory for user %s (TTL=%ds)", state["user_id"], ttl)

    return state
