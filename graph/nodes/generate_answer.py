import logging
import re
from functools import lru_cache

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from prompts.answer import build_system_prompt, build_user_prompt
from utils.llm_adapter import get_llm

logger = logging.getLogger(__name__)


@lru_cache
def _get_chat():
    return get_llm(temperature=0, max_tokens=512)


def _response_language(question: str) -> str:
    """中文问题优先使用简体中文回答，同时保留对其他语言的支持。"""
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
    prompt = build_user_prompt(
        summary=summary,
        docs=docs,
        question=question,
    )

    model_messages = [
        SystemMessage(content=build_system_prompt(lang)),
        *recent,
        HumanMessage(content=prompt),
    ]

    response = _get_chat().invoke(model_messages)
    logger.info("Generated answer for user %s (lang=%s)", state.get("user_id"), lang)

    return {
        "messages": messages + [
            HumanMessage(content=question),
            AIMessage(content=response.content),
        ]
    }
