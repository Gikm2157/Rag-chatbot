import hashlib
import logging
import os
import re
import tempfile
from datetime import datetime, timezone

import requests
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader

from config import get_settings
from db.redis_client import redis
from db.vector import get_vectorstore

logger = logging.getLogger(__name__)

# 保存所有已导入文档 ID 的 Redis 集合键。
_ALL_DOCS_KEY = "ingest:doc_ids"

# 保存 file_hash → doc_id 映射的 Redis 哈希键，用于全局重复检测，
# 可以识别使用不同 file_name 上传的相同内容。
_CONTENT_HASHES_KEY = "ingest:content_hashes"

def _file_hash(file_path: str) -> str:
    """计算整个文件的 SHA-256，用于判断文档内容是否发生变化。"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _chunk_hash(text: str) -> str:
    """计算文本块的 MD5，用于判断哪些文本块发生了变化。"""
    return hashlib.md5(text.encode()).hexdigest()


def _clean_text(text: str) -> str:
    text = re.sub(r'\n{3,}', '\n\n', text)  # 将连续 3 个以上换行压缩为 2 个
    text = re.sub(r' {2,}', ' ', text)       # 将连续多个空格压缩为 1 个
    return text.strip()


def _download_file(s3_url: str, file_name: str) -> str:
    """下载 PDF 到临时文件，检查大小限制并返回临时文件路径。"""
    setting = get_settings()
    # 配置使用便于阅读的 MB；HTTP 响应按字节计数，因此在这里换算为字节。
    max_bytes = setting.max_file_size_mb * 1024 * 1024

    try:
        # stream=True 会分块下载大文件，避免一次性将整个文件载入内存。
        response = requests.get(
            s3_url,
            timeout=setting.download_timeout_seconds,
            stream=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to download {s3_url}: {e}") from e

    # 写入临时 PDF，供只能从磁盘读取的 PyPDFLoader 使用。
    # delete=False 表示关闭文件后暂时保留，流水线结束时会在 finally 中手动删除。
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    size = 0
    with tmp:
        for chunk in response.iter_content(chunk_size=8192):
            size += len(chunk)
            if size > max_bytes:
                raise RuntimeError(f"File exceeds {setting.max_file_size_mb}MB limit")
            tmp.write(chunk)

    return tmp.name


def _get_stored_chunk_hashes(doc_id: str) -> set:
    """读取该文档上次导入时保存的文本块哈希集合。"""
    return redis.smembers(f"doc_chunks:{doc_id}")  # 键不存在时返回空集合


def _save_status(doc_id: str, **fields):
    """将导入状态保存到 Redis，供状态查询接口读取。"""
    redis.hset(f"ingest_status:{doc_id}", mapping={
        k: str(v) for k, v in fields.items()
    })


def process_policy(file_name: str, s3_url: str) -> dict:
    # doc_id 是不带 .pdf 扩展名的文档标识。例如 Company_Policy_v2.pdf 对应
    # Company_Policy_v2，同一文档的不同版本可以共用一个 ID，便于追踪内容变化。
    doc_id = file_name.rstrip(".pdf") if file_name.endswith(".pdf") else file_name
    setting = get_settings()
    file_path = None

    try:
        # ── 第 1 步：下载文件 ────────────────────────────────────────────────
        logger.info("Downloading %s", file_name)
        file_path = _download_file(s3_url, file_name)

        # ── 第 2 步：检查文件内容是否发生变化 ────────────────────────────────
        new_file_hash = _file_hash(file_path)
        stored_file_hash = redis.hget(f"ingest_status:{doc_id}", "file_hash")

        if stored_file_hash == new_file_hash:
            logger.info("Skipping %s — file unchanged", doc_id)
            return {"doc_id": doc_id, "status": "skipped", "reason": "file unchanged"}

        # ── 第 2.1 步：全局重复检测 ───────────────────────────────────────────
        # 检查完全相同的内容是否已经使用另一个 doc_id 导入。
        existing_doc_id = redis.hget(_CONTENT_HASHES_KEY, new_file_hash)
        if existing_doc_id and existing_doc_id != doc_id:
            logger.info("Skipping %s — duplicate content already ingested as %s", doc_id, existing_doc_id)
            return {
                "doc_id":  doc_id,
                "status":  "skipped",
                "reason":  f"duplicate content already ingested as '{existing_doc_id}'",
            }

        # ── 第 3 步：加载 PDF 并切分文本块 ────────────────────────────────────
        pages = PyPDFLoader(file_path).load()

        # RecursiveCharacterTextSplitter 按以下优先级尝试切分：
        # 段落（\n\n）→ 行（\n）→ 句号（.）→ 空格 → 单个字符，尽量保留完整语义。
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=100,
            separators=["\n\n", "\n", ".", " ", ""]
        )
        raw_chunks = splitter.split_documents(pages)

        # ── 第 4 步：清理文本并计算每个文本块的哈希 ──────────────────────────
        version = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        new_chunks = []  # 等待保存的 Document 对象
        new_hashes = set()  # 新版本中所有文本块的哈希

        # 逐个处理原始文本块：清理文本、跳过空内容、计算哈希，
        # 再把正文和文档 ID、页码、版本等元数据封装成 Document。
        for i, raw in enumerate(raw_chunks):
            text = _clean_text(raw.page_content)
            if not text:
                continue

            ch = _chunk_hash(text)
            new_hashes.add(ch)
            new_chunks.append(Document(
                page_content=text,
                metadata={
                    "doc_id":      doc_id,       # 用于查找该文档的全部文本块
                    "source_file": file_name,
                    "file_hash":   new_file_hash,
                    "chunk_hash":  ch,            # 用于比较单个文本块是否变化
                    "chunk_index": i,
                    "page_number": raw.metadata.get("page", 0),
                    "version":     version,
                }
            ))

        # ── 第 5 步：比较差异，只删除失效块并添加新块 ────────────────────────
        vs = get_vectorstore()
        old_hashes = _get_stored_chunk_hashes(doc_id)

        # 集合差集：stale 是旧版本存在但新版本已删除的块，fresh 是新版本新增的块。
        stale = old_hashes - new_hashes
        fresh = new_hashes - old_hashes
        # 两个集合中都存在的文本块没有变化，直接跳过以节省嵌入计算成本。

        removed = 0
        if stale:
            # 读取该文档在 ChromaDB 中的全部文本块 ID，再删除已经失效的部分。
            results = vs._collection.get(where={"doc_id": doc_id})
            stale_ids = [
                results["ids"][i]
                for i, meta in enumerate(results["metadatas"])
                if meta.get("chunk_hash") in stale
            ]
            if stale_ids:
                vs._collection.delete(ids=stale_ids)
                removed = len(stale_ids)
            logger.info("Removed %d stale chunks for %s", removed, doc_id)

        # 只为真正新增的文本块生成嵌入并保存。
        to_add = [c for c in new_chunks if c.metadata["chunk_hash"] in fresh]
        if to_add:
            vs.add_documents(to_add)
            logger.info("Added %d new chunks for %s", len(to_add), doc_id)

        # ── 第 6 步：更新 Redis 登记信息 ─────────────────────────────────────
        # 使用新版本的文本块哈希集合替换旧集合。
        redis.delete(f"doc_chunks:{doc_id}")
        if new_hashes:
            redis.sadd(f"doc_chunks:{doc_id}", *new_hashes)

        redis.sadd(_ALL_DOCS_KEY, doc_id)

        # 文档内容已变化，从全局登记表删除旧文件哈希。
        if stored_file_hash:
            redis.hdel(_CONTENT_HASHES_KEY, stored_file_hash)
        # 登记新文件哈希到 doc_id 的映射。
        redis.hset(_CONTENT_HASHES_KEY, new_file_hash, doc_id)

        _save_status(
            doc_id,
            file_hash=new_file_hash,
            file_name=file_name,
            version=version,
            status="done",
            total_chunks=len(new_chunks),
            added=len(to_add),
            removed=removed,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

        logger.info("Ingested %s — added=%d removed=%d total=%d",
                    doc_id, len(to_add), removed, len(new_chunks))

        return {
            "doc_id":  doc_id,
            "status":  "done",
            "version": version,
            "added":   len(to_add),
            "removed": removed,
            "total":   len(new_chunks),
        }

    except Exception as e:
        _save_status(doc_id, status="failed", error=str(e),
                     updated_at=datetime.now(timezone.utc).isoformat())
        logger.exception("Ingest failed for %s", doc_id)
        raise

    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
