import json
import logging

from langchain_core.messages import AIMessage, HumanMessage

from config import get_settings
from db.redis_client import redis

logger = logging.getLogger(__name__)


def store_memory(state):
    messages = state.get("messages") or []
    serialized = []

    for m in messages:
        if isinstance(m, HumanMessage):
            serialized.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage):
            serialized.append({"role": "ai", "content": m.content})

    data = {
        "summary": state.get("summary", ""),
        "messages": serialized,
    }

    ttl = get_settings().redis_ttl_seconds
    redis.set(state["user_id"], json.dumps(data), ex=ttl)
    logger.info("Stored memory for user %s (TTL=%ds)", state["user_id"], ttl)

    return state
