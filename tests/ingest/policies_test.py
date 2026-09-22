"""
文档导入流水线（ingest/policies.py）的测试。

每个测试覆盖增量导入流程的一种具体行为：
下载 → 文件级去重 → 全局去重 → 文本切分 → 差异比较 → 嵌入 → Redis 登记。

运行命令：pytest -v
"""

import pytest
import responses as resp

from ingest.policies import process_policy

URL_V1 = "https://test-bucket.s3.amazonaws.com/return_policy_v1.pdf"
URL_V2 = "https://test-bucket.s3.amazonaws.com/return_policy_v2.pdf"
FILE_NAME = "return_policy"


# ── 1. 首次导入 ──────────────────────────────────────────────────────────────

@resp.activate
def test_fresh_ingest_adds_all_chunks(pdf_v1_bytes, ingest_env):
    """首次导入文档时，每个文本块都是新增内容。"""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)

    result = process_policy(FILE_NAME, URL_V1)

    assert result["status"] == "done"
    assert result["added"] > 0
    assert result["removed"] == 0
    assert result["added"] == result["total"]


# ── 2. 文件未发生变化 ────────────────────────────────────────────────────────

@resp.activate
def test_same_file_is_skipped(pdf_v1_bytes, ingest_env):
    """连续上传完全相同的文件时，第二次调用应该跳过处理。"""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)

    process_policy(FILE_NAME, URL_V1)
    result = process_policy(FILE_NAME, URL_V1)

    assert result["status"] == "skipped"
    assert result["reason"] == "file unchanged"


# ── 3. 文件已更新：删除失效文本块 ────────────────────────────────────────────

@resp.activate
def test_update_removes_stale_chunks(pdf_v1_bytes, pdf_v2_bytes, ingest_env):
    """依次上传 v1 和 v2 后，v1 中被移除的文本块必须从 ChromaDB 删除。"""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)

    process_policy(FILE_NAME, URL_V1)
    result_v2 = process_policy(FILE_NAME, URL_V2)

    assert result_v2["status"] == "done"
    assert result_v2["removed"] > 0


# ── 4. 文件已更新：只添加新文本块 ────────────────────────────────────────────

@resp.activate
def test_update_adds_only_changed_chunks(pdf_v1_bytes, pdf_v2_bytes, ingest_env):
    """v1 和 v2 中没有变化的文本块不能重复生成嵌入。"""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)

    process_policy(FILE_NAME, URL_V1)
    result_v2 = process_policy(FILE_NAME, URL_V2)

    assert result_v2["added"] < result_v2["total"]


# ── 5. 再次上传 v2：应该跳过 ─────────────────────────────────────────────────

@resp.activate
def test_second_update_with_same_file_is_skipped(pdf_v1_bytes, pdf_v2_bytes, ingest_env):
    """按 v1 → v2 → v2 的顺序上传时，第三次调用应该跳过。"""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)

    process_policy(FILE_NAME, URL_V1)
    process_policy(FILE_NAME, URL_V2)
    result = process_policy(FILE_NAME, URL_V2)

    assert result["status"] == "skipped"


# ── 6. Redis：保存导入状态 ───────────────────────────────────────────────────

@resp.activate
def test_redis_saves_ingest_status(pdf_v1_bytes, ingest_env):
    """导入完成后，Redis 必须保存文档状态。"""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    fake_redis, _ = ingest_env

    process_policy(FILE_NAME, URL_V1)

    status = fake_redis.hgetall(f"ingest_status:{FILE_NAME}")
    assert status["status"] == "done"
    assert "file_hash" in status
    assert "version" in status
    assert "total_chunks" in status


# ── 7. Redis：文档出现在全局列表中 ───────────────────────────────────────────

@resp.activate
def test_redis_adds_doc_to_global_list(pdf_v1_bytes, ingest_env):
    """导入完成后，doc_id 必须出现在 ingest:doc_ids 集合中。"""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    fake_redis, _ = ingest_env

    process_policy(FILE_NAME, URL_V1)

    assert FILE_NAME in fake_redis.smembers("ingest:doc_ids")


# ── 8. Redis：保存文本块哈希 ─────────────────────────────────────────────────

@resp.activate
def test_redis_stores_chunk_hashes(pdf_v1_bytes, ingest_env):
    """保存的哈希数量必须等于生成的文本块总数。"""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    fake_redis, _ = ingest_env

    result = process_policy(FILE_NAME, URL_V1)

    stored = fake_redis.smembers(f"doc_chunks:{FILE_NAME}")
    assert len(stored) == result["total"]


# ── 9. ChromaDB：文本块元数据正确 ────────────────────────────────────────────

@resp.activate
def test_chunks_have_correct_metadata(pdf_v1_bytes, ingest_env):
    """每个文本块都必须包含 doc_id、chunk_hash、version 和 page_number。"""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    _, vectorstore = ingest_env

    process_policy(FILE_NAME, URL_V1)

    results = vectorstore._collection.get(where={"doc_id": FILE_NAME})
    assert len(results["ids"]) > 0
    for meta in results["metadatas"]:
        assert meta["doc_id"] == FILE_NAME
        assert meta["source_file"] == FILE_NAME
        assert "chunk_hash" in meta
        assert "version" in meta
        assert "page_number" in meta


# ── 10. ChromaDB：更新后失效文本块已删除 ─────────────────────────────────────

@resp.activate
def test_stale_chunks_removed_from_chromadb(pdf_v1_bytes, pdf_v2_bytes, ingest_env):
    """从 v1 更新到 v2 后，ChromaDB 中的数量应与 v2 文本块总数完全一致。"""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)
    _, vectorstore = ingest_env

    process_policy(FILE_NAME, URL_V1)
    result_v2 = process_policy(FILE_NAME, URL_V2)

    in_db = vectorstore._collection.get(where={"doc_id": FILE_NAME})
    assert len(in_db["ids"]) == result_v2["total"]


# ── 11. 异常：下载失败 ───────────────────────────────────────────────────────

@resp.activate
def test_download_failure_raises_runtime_error(ingest_env):
    """S3 返回非 200 状态码时必须抛出 RuntimeError。"""
    resp.add(resp.GET, URL_V1, status=403)

    with pytest.raises(RuntimeError, match="Failed to download"):
        process_policy(FILE_NAME, URL_V1)


# ── 12. 异常：将失败状态保存到 Redis ─────────────────────────────────────────

@resp.activate
def test_failed_ingest_status_saved_to_redis(ingest_env):
    """即使导入失败，也必须在 Redis 中记录失败状态。"""
    resp.add(resp.GET, URL_V1, status=500)
    fake_redis, _ = ingest_env

    with pytest.raises(RuntimeError):
        process_policy(FILE_NAME, URL_V1)

    status = fake_redis.hgetall(f"ingest_status:{FILE_NAME}")
    assert status.get("status") == "failed"
    assert "error" in status


# ── 13. 异常：文件过大 ───────────────────────────────────────────────────────

@resp.activate
def test_file_too_large_raises_error(pdf_v1_bytes, ingest_env):
    """文件超过 max_file_size_mb 限制时必须抛出 RuntimeError。"""
    from unittest.mock import patch, MagicMock
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)

    fake_settings = MagicMock()
    fake_settings.max_file_size_mb = 0
    fake_settings.download_timeout_seconds = 30

    with patch("ingest.policies.get_settings", return_value=fake_settings):
        with pytest.raises(RuntimeError, match="exceeds"):
            process_policy(FILE_NAME, URL_V1)


# ── 14. 全局重复：内容相同但 file_name 不同 ──────────────────────────────────

@resp.activate
def test_duplicate_content_different_filename_is_skipped(pdf_v1_bytes, ingest_env):
    """使用不同 file_name 上传相同 PDF 时，必须被全局哈希登记表识别。"""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)

    process_policy(FILE_NAME, URL_V1)
    result = process_policy("terms_copy", URL_V1)

    assert result["status"] == "skipped"
    assert FILE_NAME in result["reason"]


# ── 15. 导入后登记全局哈希 ───────────────────────────────────────────────────

@resp.activate
def test_global_content_hash_registered(pdf_v1_bytes, ingest_env):
    """导入完成后，文件哈希必须出现在 ingest:content_hashes 中。"""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    fake_redis, _ = ingest_env

    process_policy(FILE_NAME, URL_V1)

    registered = fake_redis.hgetall("ingest:content_hashes")
    assert FILE_NAME in registered.values()


# ── 16. 文档变化时删除旧全局哈希 ─────────────────────────────────────────────

@resp.activate
def test_old_global_hash_removed_on_update(pdf_v1_bytes, pdf_v2_bytes, ingest_env):
    """文档更新后，必须从全局登记表删除旧文件哈希。"""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)
    fake_redis, _ = ingest_env

    process_policy(FILE_NAME, URL_V1)
    v1_hash = fake_redis.hget(f"ingest_status:{FILE_NAME}", "file_hash")

    process_policy(FILE_NAME, URL_V2)

    assert fake_redis.hget("ingest:content_hashes", v1_hash) is None
    assert FILE_NAME in fake_redis.hgetall("ingest:content_hashes").values()
