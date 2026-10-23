from typing import Callable, List
from typing_extensions import NotRequired, TypedDict
from langchain_core.messages import BaseMessage

# State 是 LangGraph 流水线中各节点共享的数据容器，每个节点都可以读取并写回数据。
class State(TypedDict):
    user_id: str
    department_id: str | None
    question: str
    messages: list[BaseMessage]
    pending_messages: list[BaseMessage]
    docs: str
    summary: str
    sources: List[str]  # 本次回答使用了哪些源文档
    # 仅流式接口临时注入；普通 graph.invoke 不需要这个字段。
    stream_writer: NotRequired[Callable[[str], bool]]
