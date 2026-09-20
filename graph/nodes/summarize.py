import logging
import re
from functools import lru_cache

from langchain_core.messages import HumanMessage

from prompts.summarize import build_summarize_prompt
from utils.llm_adapter import get_llm

logger = logging.getLogger(__name__)


@lru_cache
def _get_chat():
    return get_llm(temperature=0, max_tokens=256)


def _summary_language(messages: list) -> str:
    """Match the conversation summary language to the user's language."""
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

    if len(messages) < 4:
        return state

    lang = _summary_language(messages)
    text = "\n".join(
        f"{'User' if isinstance(m, HumanMessage) else 'AI'}: {m.content}"
        for m in messages
    )

    prompt = build_summarize_prompt(text=text, lang=lang)
    summary = _get_chat().invoke(prompt)

    logger.info("Summarized conversation (%d messages, lang=%s)", len(messages), lang)

    return {
        **state,
        "summary": summary.content,
        "messages": messages[-6:],
    }
