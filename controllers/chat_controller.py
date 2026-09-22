import logging

from fastapi import APIRouter, Header, HTTPException

from schemas.chat import ChatRequest, ChatResponse
from services.chat_service import conversation

logger = logging.getLogger(__name__)
router = APIRouter()

# 从 HTTP 请求头读取 x-user-id；如果没有提供，则使用anonymous作为默认用户 ID。
@router.post("/chat", response_model=ChatResponse, summary="知识库问答")
def chat_controller(
    request: ChatRequest,
    x_user_id: str = Header(default="anonymous"),
):
    try:
        result = conversation(user_id=x_user_id, q=request.q)
        logger.info("Chat response generated for user %s", x_user_id)
        return {"status": "success", "data": result["answer"], "sources": result["sources"]}
    except Exception:
        logger.exception("Chat failed for user %s", x_user_id)
        raise HTTPException(status_code=500, detail="生成回答失败")
