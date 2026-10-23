"""
文档导入管理接口的端到端测试：
  GET  /api/v1/ingest/{doc_id}
  GET  /api/v1/ingest/docs
  DELETE /api/v1/ingest/{doc_id}

这些测试只覆盖控制器层：直接准备 Redis/ChromaDB 状态，然后验证 HTTP 响应和副作用。
导入流水线本身（下载 → 切分 → 嵌入）由 tests/ingest/policies_test.py 单独测试。

app_client、fake_redis、mock_vs 夹具均来自 conftest.py。
"""

from unittest.mock import patch


# ── GET /api/v1/ingest/{doc_id} ──────────────────────────────────────────────

def test_ingest_status_returns_doc_data(app_client, fake_redis):
    fake_redis.hset("ingest_status:my_doc", mapping={
        "status": "done",
        "file_hash": "abc123",
        "version": "2024-01-01T00:00:00Z",
        "total_chunks": "5",
    })

    resp = app_client.get("/api/v1/ingest/my_doc")

    assert resp.status_code == 200
    body = resp.json()
    assert body["doc_id"] == "my_doc"
    assert body["status"] == "done"
    assert body["file_hash"] == "abc123"
    assert body["total_chunks"] == "5"


def test_upload_endpoint_accepts_pdf(app_client):
    """上传端点应接收 multipart PDF，并把文件交给导入服务。"""
    result = {
        "doc_id": "uploaded_doc",
        "status": "done",
        "added": 1,
        "removed": 0,
        "total": 1,
    }

    with patch(
        "controllers.ingest_controller.ingest_uploaded_file",
        return_value=result,
    ) as ingest:
        resp = app_client.post(
            "/api/v1/ingest/upload",
            data={"file_name": "uploaded_doc", "department_id": "default"},
            files={"file": ("document.pdf", b"%PDF-test", "application/pdf")},
        )

    assert resp.status_code == 200
    assert resp.json()["data"]["doc_id"] == "uploaded_doc"
    ingest.assert_called_once()
    assert ingest.call_args.kwargs["department_id"] == "default"


def test_upload_rejects_unknown_department(app_client):
    with patch("controllers.ingest_controller.auth_db.get_department_by_id", return_value=None):
        response = app_client.post(
            "/api/v1/ingest/upload",
            data={"file_name": "uploaded_doc", "department_id": "missing"},
            files={"file": ("document.pdf", b"%PDF-test", "application/pdf")},
        )

    assert response.status_code == 404


def test_upload_endpoint_rejects_non_pdf(app_client):
    resp = app_client.post(
        "/api/v1/ingest/upload",
        data={"file_name": "invalid_doc"},
        files={"file": ("document.txt", b"plain text", "text/plain")},
    )

    assert resp.status_code == 422


def test_upload_endpoint_rejects_unsafe_file_name(app_client):
    resp = app_client.post(
        "/api/v1/ingest/upload",
        data={"file_name": "../secret"},
        files={"file": ("document.pdf", b"%PDF-test", "application/pdf")},
    )

    assert resp.status_code == 422


def test_ingest_status_not_found_returns_404(app_client):
    resp = app_client.get("/api/v1/ingest/does_not_exist")
    assert resp.status_code == 404


# ── GET /api/v1/ingest/docs ───────────────────────────────────────────────────

def test_list_docs_empty(app_client):
    resp = app_client.get("/api/v1/ingest/docs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["docs"] == []


def test_list_docs_returns_all_ingested(app_client, fake_redis):
    fake_redis.sadd("ingest:doc_ids", "doc_a", "doc_b")
    fake_redis.hset("ingest_status:doc_a", mapping={"status": "done", "file_name": "doc_a.pdf"})
    fake_redis.hset("ingest_status:doc_b", mapping={"status": "done", "file_name": "doc_b.pdf"})

    resp = app_client.get("/api/v1/ingest/docs")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    names = [d.get("file_name") for d in body["docs"]]
    assert "doc_a.pdf" in names
    assert "doc_b.pdf" in names


# ── DELETE /api/v1/ingest/{doc_id} ────────────────────────────────────────────

def test_delete_doc_removes_redis_keys_and_chroma_chunks(app_client, fake_redis, mock_vs):
    fake_redis.hset("ingest_status:del_doc", mapping={
        "status": "done",
        "file_hash": "hash_del",
        "file_name": "del_doc.pdf",
    })
    fake_redis.sadd("ingest:doc_ids", "del_doc")
    fake_redis.sadd("doc_chunks:del_doc", "chunk1", "chunk2")
    fake_redis.hset("ingest:content_hashes", "hash_del", "del_doc")
    mock_vs._collection.get.return_value = {
        "ids": ["chroma_id_1", "chroma_id_2"],
        "metadatas": [{}, {}],
    }

    resp = app_client.delete("/api/v1/ingest/del_doc")

    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted", "doc_id": "del_doc"}

    assert not fake_redis.exists("ingest_status:del_doc")
    assert not fake_redis.exists("doc_chunks:del_doc")
    assert "del_doc" not in fake_redis.smembers("ingest:doc_ids")
    assert fake_redis.hget("ingest:content_hashes", "hash_del") is None
    mock_vs._collection.delete.assert_called_once_with(ids=["chroma_id_1", "chroma_id_2"])


def test_employee_only_sees_and_reads_own_department_documents(
    app_client, fake_redis, set_current_user
):
    fake_redis.sadd("ingest:doc_ids", "sales_policy", "hr_policy")
    fake_redis.hset("ingest_status:sales_policy", mapping={"status": "done", "department_id": "sales"})
    fake_redis.hset("ingest_status:hr_policy", mapping={"status": "done", "department_id": "hr"})
    set_current_user(user_id="sales-employee", role="employee", department_id="sales")

    listed = app_client.get("/api/v1/ingest/docs")
    own_doc = app_client.get("/api/v1/ingest/sales_policy")
    other_doc = app_client.get("/api/v1/ingest/hr_policy")

    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert [doc["doc_id"] for doc in listed.json()["docs"]] == ["sales_policy"]
    assert own_doc.status_code == 200
    assert other_doc.status_code == 404


def test_delete_doc_with_no_chroma_chunks_still_succeeds(app_client, fake_redis, mock_vs):
    """ChromaDB 中没有文本块的文档（例如导入失败）也可以正常删除。"""
    fake_redis.hset("ingest_status:empty_doc", mapping={"status": "failed"})
    mock_vs._collection.get.return_value = {"ids": [], "metadatas": []}

    resp = app_client.delete("/api/v1/ingest/empty_doc")

    assert resp.status_code == 200
    mock_vs._collection.delete.assert_not_called()


def test_delete_doc_not_found_returns_404(app_client):
    resp = app_client.delete("/api/v1/ingest/ghost_doc")
    assert resp.status_code == 404
