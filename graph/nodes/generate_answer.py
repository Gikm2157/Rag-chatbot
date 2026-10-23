import logging
import re
from functools import lru_cache

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from config import get_settings
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


def _build_model_messages(state):
    summary = state.get("summary", "")
    messages = state.get("messages") or []
    docs = state.get("docs", "")
    question = state["question"]
    lang = _response_language(question)

    recent_limit = get_settings().memory_recent_message_limit
    recent = messages[-recent_limit:]
    prompt = build_user_prompt(
        summary=summary,
        docs=docs,
        question=question,
    )
    return [
        SystemMessage(content=build_system_prompt(lang)),
        *recent,
        HumanMessage(content=prompt),
    ], recent_limit, lang


def _chunk_content(chunk) -> str:
    content = getattr(chunk, "content", chunk)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content) if content else ""


class StreamCancelled(Exception):
    """客户端关闭连接后中止本轮回答，避免保存不完整记忆。"""


def generate_answer(state):
    model_messages, recent_limit, lang = _build_model_messages(state)
    messages = state.get("messages") or []
    pending_messages = state.get("pending_messages") or []
    question = state["question"]

    stream_writer = state.get("stream_writer")
    if stream_writer:
        chunks = []
        model_stream = iter(_get_chat().stream(model_messages))
        try:
            for chunk in model_stream:
                content = _chunk_content(chunk)
                if content:
                    chunks.append(content)
                    if stream_writer(content) is False:
                        raise StreamCancelled
        except StreamCancelled:
            close_stream = getattr(model_stream, "close", None)
            if close_stream:
                close_stream()
            raise
        answer = "".join(chunks).strip()
    else:
        response = _get_chat().invoke(model_messages)
        answer = _chunk_content(response).strip()
    # 模型有时会在回答开头或结尾带换行。这里统一清理，避免前端保留大段空白，
    # 同时确保写入 Redis 的对话记忆也是干净的文本。
    logger.info("Generated answer for user %s (lang=%s)", state.get("user_id"), lang)

    new_messages = [
        HumanMessage(content=question),
        AIMessage(content=answer),
    ]

    return {
        "messages": (messages + new_messages)[-recent_limit:],
        "pending_messages": pending_messages + new_messages,
    }
