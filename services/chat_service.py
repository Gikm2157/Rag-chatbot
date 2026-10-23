import asyncio
import json
import logging
from queue import Empty, Queue
from threading import Event, Thread

from graph.builder import build_graph
from graph.nodes.generate_answer import StreamCancelled

graph = build_graph()
logger = logging.getLogger(__name__)

def conversation(user_id: str, q: str, department_id: str | None = None):

    result = graph.invoke({
        "user_id": user_id,
        "department_id": department_id,
        "question": q
    })

    return {
        "answer": result["messages"][-1].content,
        "sources": result.get("sources", []),
    }


def _sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def stream_conversation(user_id: str, q: str, department_id: str | None = None):
    """以 SSE 输出回答；只有 LangGraph 完整结束后才保存记忆。"""
    events: Queue = Queue()
    disconnected = Event()
    finished = object()

    def write_token(content: str) -> bool:
        if disconnected.is_set():
            return False
        events.put(("token", {"content": content}))
        return True

    def run_graph() -> None:
        try:
            result = graph.invoke(
                {
                    "user_id": user_id,
                    "department_id": department_id,
                    "question": q,
                    "stream_writer": write_token,
                }
            )
            if not disconnected.is_set():
                events.put(("sources", {"sources": result.get("sources", [])}))
                events.put(("done", {"status": "success"}))
        except StreamCancelled:
            pass
        except Exception:
            logger.exception("Streaming chat failed for user %s", user_id)
            if not disconnected.is_set():
                events.put(("error", {"message": "生成回答失败"}))
        finally:
            events.put(finished)

    worker = Thread(target=run_graph, name="chat-stream", daemon=True)
    worker.start()
    try:
        while True:
            try:
                item = await asyncio.to_thread(events.get, True, 15)
            except Empty:
                yield ": keep-alive\n\n"
                continue
            if item is finished:
                break
            event, payload = item
            yield _sse_event(event, payload)
    finally:
        # 客户端断开后停止继续向队列写入；后台流程仍会自然结束，避免保存半截记忆。
        disconnected.set()
