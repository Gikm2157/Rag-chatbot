import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from dependencies.auth import get_current_user
from schemas.chat import ChatRequest, ChatResponse
from services.chat_service import conversation, stream_conversation

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/chat", response_model=ChatResponse, summary="知识库问答")
def chat_controller(
    request: ChatRequest,
    user: dict = Depends(get_current_user),
):
    try:
        if user.get("role") == "employee" and not user.get("department_id"):
            raise HTTPException(status_code=403, detail="账号尚未分配部门")
        result = conversation(
            user_id=user["id"],
            q=request.q,
            department_id=user.get("department_id"),
        )
        logger.info("Chat response generated for user %s", user["id"])
        return {"status": "success", "data": result["answer"], "sources": result["sources"]}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Chat failed for user %s", user["id"])
        raise HTTPException(status_code=500, detail="生成回答失败")


@router.post("/chat/stream", summary="流式知识库问答")
def chat_stream_controller(
    request: ChatRequest,
    user: dict = Depends(get_current_user),
):
    if user.get("role") == "employee" and not user.get("department_id"):
        raise HTTPException(status_code=403, detail="账号尚未分配部门")

    return StreamingResponse(
        stream_conversation(
            user_id=user["id"],
            q=request.q,
            department_id=user.get("department_id"),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
