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
    # We keep track of all ingested document IDs in a Redis set called "ingest:doc_ids". To list all documents, we fetch all doc IDs from that set, then retrieve the status hash for each doc ID.
    doc_ids = sorted(redis.smembers("ingest:doc_ids"))
    page = doc_ids[offset : offset + limit]
    docs = [{"doc_id": doc_id, **redis.hgetall(f"ingest_status:{doc_id}")} for doc_id in page]
    return {"total": len(doc_ids), "docs": docs}


# NOTE: must stay registered after /ingest/docs above — Starlette matches
# routes in registration order, so a dynamic {doc_id} route declared first
# would swallow requests to /ingest/docs (treating "docs" as a doc_id).
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
    # Check the document actually exists before attempting cleanup
    status = redis.hgetall(f"ingest_status:{doc_id}")
    if not status:
        raise HTTPException(status_code=404, detail=f"未找到文档 '{doc_id}'")

    # 1. Remove all chunks for this doc from ChromaDB
    vs = get_vectorstore()
    results = vs._collection.get(where={"doc_id": doc_id})
    if results["ids"]:
        vs._collection.delete(ids=results["ids"])
        logger.info("Deleted %d chunks from ChromaDB for %s", len(results["ids"]), doc_id)

    # 2. Remove file hash from global content-hash registry so the same
    #    PDF can be re-ingested under a new name later without being blocked
    file_hash = status.get("file_hash")
    if file_hash:
        redis.hdel("ingest:content_hashes", file_hash)

    # 3. Clean up all per-document Redis keys
    redis.delete(f"ingest_status:{doc_id}")
    redis.delete(f"doc_chunks:{doc_id}")
    redis.srem("ingest:doc_ids", doc_id)

    logger.info("Deleted document %s", doc_id)
    return {"status": "deleted", "doc_id": doc_id}
