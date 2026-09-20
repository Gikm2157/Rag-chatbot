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

    # Placeholder for a string value (user_id). The %s in the log message will be replaced by this value (user_id) when the log is recorded. The %d is a placeholder for an integer value (number of messages). The logger will automatically convert the number of messages to an integer when formatting the log message.
    logger.info("Loaded memory for user %s (%d messages)", user_id, len(messages))
    return {"messages": messages, "summary": data.get("summary", "")}
