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

# Redis key that holds the set of all ingested doc_ids
_ALL_DOCS_KEY = "ingest:doc_ids"

# Redis hash that maps file_hash → doc_id for global duplicate detection.
# Catches the same content uploaded under a different file_name.
_CONTENT_HASHES_KEY = "ingest:content_hashes"

# this below fucntion gives you a unique identifier for the file's content. even if small change happens in the file, the hash will be different, so you know the file was updated and needs to be reprocessed.if there is no change in the file, the hash will be the same, so you can skip reprocessing and save time and resources.
def _file_hash(file_path: str) -> str:
    """SHA-256 of the full file. Used to detect if a document changed at all."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _chunk_hash(text: str) -> str:
    """MD5 of a chunk's text. Used to detect which chunks changed."""
    return hashlib.md5(text.encode()).hexdigest()


def _clean_text(text: str) -> str:
    text = re.sub(r'\n{3,}', '\n\n', text)  # collapse 3+ newlines to 2
    text = re.sub(r' {2,}', ' ', text)       # collapse multiple spaces to 1
    return text.strip()


def _download_file(s3_url: str, file_name: str) -> str:
    """Download PDF to a temp file, enforce size limit, return the temp path."""
    setting = get_settings()
    # max_file_size_mb is a user-friendly setting (e.g. "10" for 10 megabytes). We convert it to bytes here because that's what we get from the HTTP response.
    max_bytes = setting.max_file_size_mb * 1024 * 1024

    try:
        # Why stream=True? beacuse To handle large files without loading them entirely into memory mean Downloads little-by-little in chunks.
        response = requests.get(
            s3_url,
            timeout=setting.download_timeout_seconds,
            stream=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to download {s3_url}: {e}") from e

    # write to a temp file so PyPDFLoader can read it from disk
    # tempfile.NamedTemporaryFile creates a temp file that we can write to. We specify suffix=".pdf" so it has the right extension. delete=False means we want to keep the file after closing it (we'll delete it manually later).
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
    """Load the set of chunk hashes we stored last time this doc was ingested."""
    return redis.smembers(f"doc_chunks:{doc_id}")  # returns empty set if key missing


def _save_status(doc_id: str, **fields):
    """Save ingest status to Redis so we can query it via the status endpoint."""
    redis.hset(f"ingest_status:{doc_id}", mapping={
        k: str(v) for k, v in fields.items()
    })


def process_policy(file_name: str, s3_url: str) -> dict:
    # doc_id is a clean identifier — strip the .pdf extension if present
    # what is the doc_id for "Company_Policy_v2.pdf"? it's "Company_Policy_v2". This lets us keep all versions of the same document under one doc_id, which makes it easier to track changes over time.
    doc_id = file_name.rstrip(".pdf") if file_name.endswith(".pdf") else file_name
    setting = get_settings()
    file_path = None

    try:
        # ── Step 1: download ──────────────────────────────────────────────────
        logger.info("Downloading %s", file_name)
        file_path = _download_file(s3_url, file_name)

        # ── Step 2: check if file actually changed ────────────────────────────
        new_file_hash = _file_hash(file_path)
        stored_file_hash = redis.hget(f"ingest_status:{doc_id}", "file_hash")

        if stored_file_hash == new_file_hash:
            logger.info("Skipping %s — file unchanged", doc_id)
            return {"doc_id": doc_id, "status": "skipped", "reason": "file unchanged"}

        # ── Step 2b: global duplicate check ──────────────────────────────────
        # Check if this exact content already exists under a DIFFERENT doc_id.
        # e.g. "return_policy" and "terms_v2" uploaded with the same PDF content.
        existing_doc_id = redis.hget(_CONTENT_HASHES_KEY, new_file_hash)
        if existing_doc_id and existing_doc_id != doc_id:
            logger.info("Skipping %s — duplicate content already ingested as %s", doc_id, existing_doc_id)
            return {
                "doc_id":  doc_id,
                "status":  "skipped",
                "reason":  f"duplicate content already ingested as '{existing_doc_id}'",
            }

        # ── Step 3: load PDF and split into chunks ────────────────────────────
        pages = PyPDFLoader(file_path).load()

        # RecursiveCharacterTextSplitter tries these separators in order:
        # paragraph (\n\n) → line (\n) → sentence (.) → word ( ) → character ("")
        # This means it NEVER cuts a sentence in half — much better context quality
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=100,
            separators=["\n\n", "\n", ".", " ", ""]
        )
        raw_chunks = splitter.split_documents(pages)

        # ── Step 4: clean text and compute a hash for each chunk ──────────────
        version = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        new_chunks = []   # Document objects ready to store
        new_hashes = set()  # hash for every chunk in the new version

        # explain me below code in detail.
        # here is the code iterates over each raw chunk extracted from the PDF. For each chunk, it performs the following steps:
        # 1. Cleans the text using the _clean_text function, which collapses multiple newlines and spaces to improve readability.
        # 2. If the cleaned text is empty, it skips to the next chunk (this can happen if the chunk was just whitespace).
        # 3. Computes a unique hash for the chunk's text using the _chunk_hash function. This hash will be used later to determine if the chunk has changed since the last ingest.
        # 4. Creates a Document object for the chunk, which includes the cleaned text and metadata such as the doc_id, source file name, file hash, chunk hash, chunk index, page number, and version timestamp.
        # 5. Adds the chunk's hash to the new_hashes set and the Document object to the new_chunks list for further processing (like embedding and storage).
        for i, raw in enumerate(raw_chunks):
            text = _clean_text(raw.page_content)
            if not text:
                continue

            ch = _chunk_hash(text)
            new_hashes.add(ch)
            new_chunks.append(Document(
                page_content=text,
                metadata={
                    "doc_id":      doc_id,       # lets us find all chunks for this doc
                    "source_file": file_name,
                    "file_hash":   new_file_hash,
                    "chunk_hash":  ch,            # lets us diff individual chunks
                    "chunk_index": i,
                    "page_number": raw.metadata.get("page", 0),
                    "version":     version,
                }
            ))

        # ── Step 5: diff — only delete stale chunks, only add new ones ────────
        vs = get_vectorstore()
        old_hashes = _get_stored_chunk_hashes(doc_id)

        # set subtraction:
        # stale = chunks that existed before but are gone in the new version
        # fresh = chunks that are new in this version (not in the old one)
        stale = old_hashes - new_hashes
        fresh = new_hashes - old_hashes
        # chunks in both sets are unchanged — we skip them entirely (no cost)

        removed = 0
        if stale:
            # fetch all chunk IDs in ChromaDB for this doc, then delete the stale ones
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

        # only embed and store chunks that are actually new
        to_add = [c for c in new_chunks if c.metadata["chunk_hash"] in fresh]
        if to_add:
            vs.add_documents(to_add)
            logger.info("Added %d new chunks for %s", len(to_add), doc_id)

        # ── Step 6: update Redis registry ────────────────────────────────────
        # replace old chunk hash set with new one
        redis.delete(f"doc_chunks:{doc_id}")
        if new_hashes:
            redis.sadd(f"doc_chunks:{doc_id}", *new_hashes)

        redis.sadd(_ALL_DOCS_KEY, doc_id)

        # remove old file hash from global registry (doc content changed)
        if stored_file_hash:
            redis.hdel(_CONTENT_HASHES_KEY, stored_file_hash)
        # register new file hash → this doc_id
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
