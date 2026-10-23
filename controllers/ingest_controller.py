import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from dependencies.auth import get_current_user, require_admin
from db import auth_db
from db.redis_client import redis
from db.vector import get_vectorstore
from schemas.ingest import (
    DeleteResponse,
    DocListResponse,
    DocStatus,
    IngestRequest,
    IngestResponse,
)
from schemas.ingest import validate_file_name
from services.ingest_service import ingest_file, ingest_uploaded_file

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="导入 PDF 文档",
    dependencies=[Depends(require_admin)],
)
def ingest(request: IngestRequest):
    if not auth_db.get_department_by_id(request.department_id):
        raise HTTPException(status_code=404, detail="部门不存在")
    try:
        result = ingest_file(
            request.file_name,
            str(request.s3_url),
            department_id=request.department_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        logger.exception("Ingest failed for %s", request.file_name)
        raise HTTPException(status_code=500, detail="文档导入失败")
    return {"status": "success", "data": result}


@router.post(
    "/ingest/upload",
    response_model=IngestResponse,
    summary="上传并导入本地 PDF",
    dependencies=[Depends(require_admin)],
)
def ingest_upload(
    file_name: str = Form(..., description="文档 ID，不含扩展名"),
    department_id: str = Form("default", description="文档所属部门"),
    file: UploadFile = File(..., description="要导入的 PDF 文件"),
):
    """接收前端上传的 PDF，并复用现有增量导入流程。"""
    try:
        file_name = validate_file_name(file_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="上传文件必须是 PDF")
    if not auth_db.get_department_by_id(department_id):
        raise HTTPException(status_code=404, detail="部门不存在")

    try:
        result = ingest_uploaded_file(
            file_name,
            file.file,
            department_id=department_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        logger.exception("Uploaded ingest failed for %s", file_name)
        raise HTTPException(status_code=500, detail="文档导入失败")
    return {"status": "success", "data": result}


@router.get(
    "/ingest/docs",
    response_model=DocListResponse,
    summary="查看已导入文档",
    dependencies=[Depends(get_current_user)],
)
def list_docs(limit: int = 50, offset: int = 0, user: dict = Depends(get_current_user)):
    """管理员查看全部文档；员工只能看到所属部门文档。"""
    # Redis 集合 ingest:doc_ids 保存所有已导入文档 ID；先读取这些 ID，再逐个查询状态。
    all_doc_ids = sorted(redis.smembers("ingest:doc_ids"))
    visible_docs = []
    for doc_id in all_doc_ids:
        status = redis.hgetall(f"ingest_status:{doc_id}")
        department_id = status.get("department_id", "default")
        if user.get("role") == "admin" or department_id == user.get("department_id", "default"):
            visible_docs.append({"doc_id": doc_id, **status})
    page = visible_docs[offset : offset + limit]
    return {"total": len(visible_docs), "docs": page}


# 注意：该动态路由必须注册在 /ingest/docs 之后。Starlette 按注册顺序匹配路由；
# 如果先注册 {doc_id}，/ingest/docs 中的 docs 会被误当作 doc_id。
@router.get(
    "/ingest/{doc_id}",
    response_model=DocStatus,
    summary="查看文档状态",
    dependencies=[Depends(get_current_user)],
)
def get_doc(doc_id: str, user: dict = Depends(get_current_user)):
    """查看指定文档的导入状态。"""
    status = redis.hgetall(f"ingest_status:{doc_id}")
    if not status:
        raise HTTPException(status_code=404, detail=f"未找到文档 '{doc_id}'")
    if user.get("role") != "admin" and status.get("department_id", "default") != user.get("department_id", "default"):
        raise HTTPException(status_code=404, detail=f"未找到文档 '{doc_id}'")
    return {"doc_id": doc_id, **status}


@router.delete(
    "/ingest/{doc_id}",
    response_model=DeleteResponse,
    summary="删除文档",
    dependencies=[Depends(require_admin)],
)
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
        department_id = status.get("department_id", "default")
        redis.hdel(
            "ingest:content_hashes",
            file_hash if department_id == "default" else f"{department_id}:{file_hash}",
        )

    # 3. 清理该文档在 Redis 中的所有记录。
    redis.delete(f"ingest_status:{doc_id}")
    redis.delete(f"doc_chunks:{doc_id}")
    redis.srem("ingest:doc_ids", doc_id)

    logger.info("Deleted document %s", doc_id)
    return {"status": "deleted", "doc_id": doc_id}
