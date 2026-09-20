"""
Tests for the ingest pipeline (ingest/policies.py).

Each test covers one specific behaviour of the incremental ingestion flow:
download → file-level dedup → global dedup → chunk → diff → embed → Redis registry.

Run with:  pytest -v
"""

import pytest
import responses as resp

from ingest.policies import process_policy

URL_V1 = "https://test-bucket.s3.amazonaws.com/return_policy_v1.pdf"
URL_V2 = "https://test-bucket.s3.amazonaws.com/return_policy_v2.pdf"
FILE_NAME = "return_policy"


# ── 1. Fresh ingest ───────────────────────────────────────────────────────────

@resp.activate
def test_fresh_ingest_adds_all_chunks(pdf_v1_bytes, ingest_env):
    """First time a document is ingested — every chunk is new."""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)

    result = process_policy(FILE_NAME, URL_V1)

    assert result["status"] == "done"
    assert result["added"] > 0
    assert result["removed"] == 0
    assert result["added"] == result["total"]


# ── 2. Unchanged file ─────────────────────────────────────────────────────────

@resp.activate
def test_same_file_is_skipped(pdf_v1_bytes, ingest_env):
    """Upload the exact same file twice — second call should be skipped."""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)

    process_policy(FILE_NAME, URL_V1)
    result = process_policy(FILE_NAME, URL_V1)

    assert result["status"] == "skipped"
    assert result["reason"] == "file unchanged"


# ── 3. Updated file — stale chunks removed ───────────────────────────────────

@resp.activate
def test_update_removes_stale_chunks(pdf_v1_bytes, pdf_v2_bytes, ingest_env):
    """Upload v1 then v2 — chunks removed from v1 must be deleted from ChromaDB."""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)

    process_policy(FILE_NAME, URL_V1)
    result_v2 = process_policy(FILE_NAME, URL_V2)

    assert result_v2["status"] == "done"
    assert result_v2["removed"] > 0


# ── 4. Updated file — only new chunks added ───────────────────────────────────

@resp.activate
def test_update_adds_only_changed_chunks(pdf_v1_bytes, pdf_v2_bytes, ingest_env):
    """Unchanged chunks between v1 and v2 must not be re-embedded."""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)

    process_policy(FILE_NAME, URL_V1)
    result_v2 = process_policy(FILE_NAME, URL_V2)

    assert result_v2["added"] < result_v2["total"]


# ── 5. Re-upload v2 after v2 — should skip ───────────────────────────────────

@resp.activate
def test_second_update_with_same_file_is_skipped(pdf_v1_bytes, pdf_v2_bytes, ingest_env):
    """v1 → v2 → v2 again — third call should be skipped."""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)

    process_policy(FILE_NAME, URL_V1)
    process_policy(FILE_NAME, URL_V2)
    result = process_policy(FILE_NAME, URL_V2)

    assert result["status"] == "skipped"


# ── 6. Redis — status is saved ────────────────────────────────────────────────

@resp.activate
def test_redis_saves_ingest_status(pdf_v1_bytes, ingest_env):
    """After ingest, Redis must hold the document's status."""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    fake_redis, _ = ingest_env

    process_policy(FILE_NAME, URL_V1)

    status = fake_redis.hgetall(f"ingest_status:{FILE_NAME}")
    assert status["status"] == "done"
    assert "file_hash" in status
    assert "version" in status
    assert "total_chunks" in status


# ── 7. Redis — doc appears in global list ────────────────────────────────────

@resp.activate
def test_redis_adds_doc_to_global_list(pdf_v1_bytes, ingest_env):
    """After ingest, the doc_id must appear in the 'ingest:doc_ids' set."""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    fake_redis, _ = ingest_env

    process_policy(FILE_NAME, URL_V1)

    assert FILE_NAME in fake_redis.smembers("ingest:doc_ids")


# ── 8. Redis — chunk hashes stored ───────────────────────────────────────────

@resp.activate
def test_redis_stores_chunk_hashes(pdf_v1_bytes, ingest_env):
    """Number of stored hashes must equal total chunks produced."""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    fake_redis, _ = ingest_env

    result = process_policy(FILE_NAME, URL_V1)

    stored = fake_redis.smembers(f"doc_chunks:{FILE_NAME}")
    assert len(stored) == result["total"]


# ── 9. ChromaDB — chunk metadata is correct ──────────────────────────────────

@resp.activate
def test_chunks_have_correct_metadata(pdf_v1_bytes, ingest_env):
    """Every stored chunk must carry doc_id, chunk_hash, version, page_number."""
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


# ── 10. ChromaDB — stale chunks are gone after update ────────────────────────

@resp.activate
def test_stale_chunks_removed_from_chromadb(pdf_v1_bytes, pdf_v2_bytes, ingest_env):
    """After v1 → v2, ChromaDB should hold exactly the v2 chunk count."""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)
    _, vectorstore = ingest_env

    process_policy(FILE_NAME, URL_V1)
    result_v2 = process_policy(FILE_NAME, URL_V2)

    in_db = vectorstore._collection.get(where={"doc_id": FILE_NAME})
    assert len(in_db["ids"]) == result_v2["total"]


# ── 11. Error — download failure ─────────────────────────────────────────────

@resp.activate
def test_download_failure_raises_runtime_error(ingest_env):
    """Non-200 S3 response must raise RuntimeError."""
    resp.add(resp.GET, URL_V1, status=403)

    with pytest.raises(RuntimeError, match="Failed to download"):
        process_policy(FILE_NAME, URL_V1)


# ── 12. Error — failed status saved to Redis ─────────────────────────────────

@resp.activate
def test_failed_ingest_status_saved_to_redis(ingest_env):
    """Even when ingest fails, the failure must be recorded in Redis."""
    resp.add(resp.GET, URL_V1, status=500)
    fake_redis, _ = ingest_env

    with pytest.raises(RuntimeError):
        process_policy(FILE_NAME, URL_V1)

    status = fake_redis.hgetall(f"ingest_status:{FILE_NAME}")
    assert status.get("status") == "failed"
    assert "error" in status


# ── 13. Error — file too large ────────────────────────────────────────────────

@resp.activate
def test_file_too_large_raises_error(pdf_v1_bytes, ingest_env):
    """File exceeding max_file_size_mb must raise RuntimeError."""
    from unittest.mock import patch, MagicMock
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)

    fake_settings = MagicMock()
    fake_settings.max_file_size_mb = 0
    fake_settings.download_timeout_seconds = 30

    with patch("ingest.policies.get_settings", return_value=fake_settings):
        with pytest.raises(RuntimeError, match="exceeds"):
            process_policy(FILE_NAME, URL_V1)


# ── 14. Global duplicate — same content, different file_name ─────────────────

@resp.activate
def test_duplicate_content_different_filename_is_skipped(pdf_v1_bytes, ingest_env):
    """Same PDF under a different file_name must be caught by the global hash registry."""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)

    process_policy(FILE_NAME, URL_V1)
    result = process_policy("terms_copy", URL_V1)

    assert result["status"] == "skipped"
    assert FILE_NAME in result["reason"]


# ── 15. Global hash registered after ingest ───────────────────────────────────

@resp.activate
def test_global_content_hash_registered(pdf_v1_bytes, ingest_env):
    """After ingest, the file hash must appear in 'ingest:content_hashes'."""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    fake_redis, _ = ingest_env

    process_policy(FILE_NAME, URL_V1)

    registered = fake_redis.hgetall("ingest:content_hashes")
    assert FILE_NAME in registered.values()


# ── 16. Old global hash removed when doc content changes ─────────────────────

@resp.activate
def test_old_global_hash_removed_on_update(pdf_v1_bytes, pdf_v2_bytes, ingest_env):
    """When a document is updated, the old file hash must leave the global registry."""
    resp.add(resp.GET, URL_V1, body=pdf_v1_bytes, status=200)
    resp.add(resp.GET, URL_V2, body=pdf_v2_bytes, status=200)
    fake_redis, _ = ingest_env

    process_policy(FILE_NAME, URL_V1)
    v1_hash = fake_redis.hget(f"ingest_status:{FILE_NAME}", "file_hash")

    process_policy(FILE_NAME, URL_V2)

    assert fake_redis.hget("ingest:content_hashes", v1_hash) is None
    assert FILE_NAME in fake_redis.hgetall("ingest:content_hashes").values()
