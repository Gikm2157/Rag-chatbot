from typing import List
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage

# State 是 LangGraph 流水线中各节点共享的数据容器，每个节点都可以读取并写回数据。
class State(TypedDict):
    user_id: str
    question: str
    messages: list[BaseMessage]
    pending_messages: list[BaseMessage]
    docs: str
    summary: str
    sources: List[str]  # 本次回答使用了哪些源文档
