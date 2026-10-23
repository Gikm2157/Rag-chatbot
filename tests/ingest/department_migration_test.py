from unittest.mock import MagicMock, patch

from ingest.policies import migrate_legacy_department_metadata


def test_legacy_documents_are_assigned_to_default_department(fake_redis):
    fake_redis.sadd("ingest:doc_ids", "old_policy")
    fake_redis.hset("ingest_status:old_policy", mapping={"status": "done", "file_hash": "hash-1"})
    fake_redis.hset("ingest:content_hashes", "hash-1", "old_policy")
    collection = MagicMock()
    collection.get.side_effect = [
        {
            "ids": ["chunk-1"],
            "metadatas": [{"doc_id": "old_policy", "chunk_hash": "chunk-hash"}],
        },
        {"ids": [], "metadatas": []},
    ]

    with patch("ingest.policies.redis", fake_redis), patch(
        "ingest.policies.get_vectorstore", return_value=MagicMock(_collection=collection)
    ):
        migrate_legacy_department_metadata()
        migrate_legacy_department_metadata()

    assert fake_redis.hget("ingest_status:old_policy", "department_id") == "default"
    assert fake_redis.hget("ingest:content_hashes", "hash-1") == "old_policy"
    collection.update.assert_called_once_with(
        ids=["chunk-1"],
        metadatas=[
            {"doc_id": "old_policy", "chunk_hash": "chunk-hash", "department_id": "default"}
        ],
    )
    assert collection.get.call_count == 1
