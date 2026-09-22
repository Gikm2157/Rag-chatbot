import logging

from fastapi import APIRouter, HTTPException

from db.redis_client import redis
from db.vector import get_vectorstore
from schemas.ingest import (
    DeleteResponse,
    DocListResponse,
    DocStatus,
    IngestRequest,
    IngestResponse,
)
from services.ingest_service import ingest_file

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/ingest", response_model=IngestResponse, summary="导入 PDF 文档")
def ingest(request: IngestRequest):
    try:
        result = ingest_file(request.file_name, str(request.s3_url))
        return {"status": "success", "data": result}
    except Exception:
        logger.exception("Ingest failed for %s", request.file_name)
        raise HTTPException(status_code=500, detail="文档导入失败")


@router.get("/ingest/docs", response_model=DocListResponse, summary="查看已导入文档")
def list_docs(limit: int = 50, offset: int = 0):
    """查看所有已导入文档及其当前状态。"""
    # Redis 集合 ingest:doc_ids 保存所有已导入文档 ID；先读取这些 ID，再逐个查询状态。
    doc_ids = sorted(redis.smembers("ingest:doc_ids"))
    page = doc_ids[offset : offset + limit]
    docs = [{"doc_id": doc_id, **redis.hgetall(f"ingest_status:{doc_id}")} for doc_id in page]
    return {"total": len(doc_ids), "docs": docs}


# 注意：该动态路由必须注册在 /ingest/docs 之后。Starlette 按注册顺序匹配路由；
# 如果先注册 {doc_id}，/ingest/docs 中的 docs 会被误当作 doc_id。
@router.get("/ingest/{doc_id}", response_model=DocStatus, summary="查看文档状态")
def get_doc(doc_id: str):
    """查看指定文档的导入状态。"""
    status = redis.hgetall(f"ingest_status:{doc_id}")
    if not status:
        raise HTTPException(status_code=404, detail=f"未找到文档 '{doc_id}'")
    return {"doc_id": doc_id, **status}


@router.delete("/ingest/{doc_id}", response_model=DeleteResponse, summary="删除文档")
def delete_doc(doc_id: str):
    """从知识库和 Redis 记录中删除指定文档。"""
    # 执行清理前先确认文档确实存在。
    status = redis.hgetall(f"ingest_status:{doc_id}")
    if not status:
        raise HTTPException(status_code=404, detail=f"未找到文档 '{doc_id}'")

    # 1. 从 ChromaDB 删除该文档的所有文本块。
    vs = get_vectorstore()
    results = vs._collection.get(where={"doc_id": doc_id})
    if results["ids"]:
        vs._collection.delete(ids=results["ids"])
        logger.info("Deleted %d chunks from ChromaDB for %s", len(results["ids"]), doc_id)

    # 2. 从全局内容哈希表删除文件哈希，允许以后用新名称重新导入同一 PDF。
    file_hash = status.get("file_hash")
    if file_hash:
        redis.hdel("ingest:content_hashes", file_hash)

    # 3. 清理该文档在 Redis 中的所有记录。
    redis.delete(f"ingest_status:{doc_id}")
    redis.delete(f"doc_chunks:{doc_id}")
    redis.srem("ingest:doc_ids", doc_id)

    logger.info("Deleted document %s", doc_id)
    return {"status": "deleted", "doc_id": doc_id}
