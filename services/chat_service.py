from graph.builder import build_graph
from langchain_core.messages import HumanMessage

graph = build_graph()

def conversation(user_id: str, q: str):

    result = graph.invoke({
        "user_id": user_id,
        "question": q
    })

    return {
        "answer": result["messages"][-1].content,
        "sources": result.get("sources", []),
    }