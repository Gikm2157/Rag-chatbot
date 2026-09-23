import logging
import re
from functools import lru_cache

from langchain_core.messages import HumanMessage

from config import get_settings
from prompts.summarize import build_summarize_prompt
from utils.llm_adapter import get_llm

logger = logging.getLogger(__name__)


@lru_cache
def _get_chat():
    return get_llm(temperature=0, max_tokens=256)


def _summary_language(messages: list) -> str:
    """让对话摘要使用与用户相同的语言。"""
    user_text = " ".join(
        m.content for m in messages if isinstance(m, HumanMessage)
    )
    if re.search(r"[\u4e00-\u9fff]", user_text):
        return "Simplified Chinese"
    if re.search(r"[\u0600-\u06ff]", user_text):
        return "Arabic"
    return "English"


def summarize(state):
    messages = state.get("messages") or []
    pending_messages = state.get("pending_messages") or []
    trigger_count = get_settings().summary_trigger_message_count

    if len(pending_messages) < trigger_count:
        return state

    lang = _summary_language(pending_messages)
    text = "\n".join(
        f"{'User' if isinstance(m, HumanMessage) else 'AI'}: {m.content}"
        for m in pending_messages
    )

    prompt = build_summarize_prompt(
        previous_summary=state.get("summary", ""),
        new_messages=text,
        lang=lang,
    )
    summary = _get_chat().invoke(prompt)

    logger.info(
        "Updated conversation summary with %d new messages (lang=%s)",
        len(pending_messages),
        lang,
    )

    return {
        **state,
        "summary": summary.content,
        "messages": messages,
        "pending_messages": [],
    }
