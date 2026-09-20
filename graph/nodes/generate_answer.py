import logging
import re
from functools import lru_cache

from langchain_core.messages import AIMessage, HumanMessage

from prompts.answer import build_answer_prompt
from utils.llm_adapter import get_llm

logger = logging.getLogger(__name__)


@lru_cache
def _get_chat():
    return get_llm(temperature=0, max_tokens=512)


def _response_language(question: str) -> str:
    """Prefer Chinese for Chinese questions while preserving existing languages."""
    if re.search(r"[\u4e00-\u9fff]", question):
        return "Simplified Chinese"
    if re.search(r"[\u0600-\u06ff]", question):
        return "Arabic"
    return "English"


def generate_answer(state):
    summary = state.get("summary", "")
    messages = state.get("messages") or []
    docs = state.get("docs", "")
    question = state["question"]
    lang = _response_language(question)

    recent = messages[-6:]
    history = "\n".join(
        f"{'User' if isinstance(m, HumanMessage) else 'AI'}: {m.content}"
        for m in recent
    )

    prompt = build_answer_prompt(
        summary=summary,
        history=history,
        docs=docs,
        question=question,
        lang=lang,
    )

    response = _get_chat().invoke(prompt)
    logger.info("Generated answer for user %s (lang=%s)", state.get("user_id"), lang)

    return {
        "messages": messages + [
            HumanMessage(content=question),
            AIMessage(content=response.content),
        ]
    }
