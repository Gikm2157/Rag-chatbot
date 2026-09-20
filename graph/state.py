from typing import List
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage

# What is State? It's a shared bag of data that gets passed between every node in the LangGraph pipeline. Each node reads from it and writes back to it.
class State(TypedDict):
    user_id: str
    question: str
    messages: list[BaseMessage]
    docs: str
    summary: str
    sources: List[str]  # which documents were used to answer