"""
conftest.py — shared fixtures for all tests.

pytest automatically loads this file before running any test.
Fixtures defined here are available to every test file without importing them.
"""

import pytest
import fakeredis
from fpdf import FPDF
from unittest.mock import MagicMock, patch
from langchain_chroma import Chroma


# ── Test document content ─────────────────────────────────────────────────────
# Two versions of the same policy.
# V2 has two paragraphs changed (30→60 days return window, 5-7→3-5 day refund).
# The other paragraphs are identical — so the diff should only touch the changed ones.

# Policies are long enough to produce multiple chunks at chunk_size=800.
# Sections marked CHANGED differ between v1 and v2.
# Sections marked UNCHANGED are identical — those chunks must be skipped on re-ingest.

POLICY_V1 = """\
Return Policy

Customers may return any item within 30 days of purchase for a full refund.
To initiate a return, customers must contact our support team at support@company.com
and provide the original order number, proof of purchase, and a brief description
of the reason for the return. Returns without prior authorization will not be accepted.
Items must be in their original condition, unused, and in the original packaging.

Damaged or defective items must be reported within 24 hours of delivery.
Customers should photograph the damage and attach the images when contacting support.
Failure to report damage within the specified window may result in the claim being denied.
Our team will review each case individually and respond within two business days.

Refunds are processed within 5 to 7 business days after the returned item is received.
Refunds will be issued to the original payment method only. If the original payment
method is no longer available, store credit will be issued instead. Shipping fees are
non-refundable unless the return is due to our error or a defective product.

Exchange Policy

Items may be exchanged within 14 days of purchase. Original receipt required.
Exchanges are subject to product availability. If the requested item is out of stock,
customers may choose an alternative product of equal value or receive a store credit.
Exchanges must be initiated through our online portal or by visiting a physical store.

Shipping Policy

All orders are processed within 1 to 2 business days after payment confirmation.
Standard shipping takes 5 to 7 business days. Express shipping is available for an
additional fee and delivers within 2 to 3 business days. International orders may
take 10 to 20 business days depending on customs clearance in the destination country.
Customers will receive a tracking number by email once the order has been dispatched.

Privacy and Data Policy

We collect personal data only for the purpose of processing your order and improving
our services. Your data will never be sold to third parties. Customers may request
deletion of their data at any time by contacting privacy@company.com. We comply with
all applicable data protection regulations including GDPR and local privacy laws.
"""

# CHANGED: return window (30→60 days), refund timeline (5-7→3-5 days)
# UNCHANGED: exchange policy, shipping policy, privacy policy
POLICY_V2 = """\
Return Policy

Customers may return any item within 60 days of purchase for a full refund.
To initiate a return, customers must contact our support team at support@company.com
and provide the original order number, proof of purchase, and a brief description
of the reason for the return. Returns without prior authorization will not be accepted.
Items must be in their original condition, unused, and in the original packaging.

Damaged or defective items must be reported within 24 hours of delivery.
Customers should photograph the damage and attach the images when contacting support.
Failure to report damage within the specified window may result in the claim being denied.
Our team will review each case individually and respond within two business days.

Refunds are processed within 3 to 5 business days after the returned item is received.
Refunds will be issued to the original payment method only. If the original payment
method is no longer available, store credit will be issued instead. Shipping fees are
non-refundable unless the return is due to our error or a defective product.

Exchange Policy

Items may be exchanged within 14 days of purchase. Original receipt required.
Exchanges are subject to product availability. If the requested item is out of stock,
customers may choose an alternative product of equal value or receive a store credit.
Exchanges must be initiated through our online portal or by visiting a physical store.

Shipping Policy

All orders are processed within 1 to 2 business days after payment confirmation.
Standard shipping takes 5 to 7 business days. Express shipping is available for an
additional fee and delivers within 2 to 3 business days. International orders may
take 10 to 20 business days depending on customs clearance in the destination country.
Customers will receive a tracking number by email once the order has been dispatched.

Privacy and Data Policy

We collect personal data only for the purpose of processing your order and improving
our services. Your data will never be sold to third parties. Customers may request
deletion of their data at any time by contacting privacy@company.com. We comply with
all applicable data protection regulations including GDPR and local privacy laws.
"""


def _make_pdf_bytes(text: str) -> bytes:
    """
    Build a real PDF from plain text and return its bytes.
    fpdf2 is a lightweight library — no external tools needed.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for paragraph in text.strip().split("\n\n"):
        pdf.multi_cell(0, 8, paragraph.strip())
        pdf.ln(4)
    return bytes(pdf.output())


# ── PDF fixtures ──────────────────────────────────────────────────────────────
# scope="session" means the PDF bytes are generated once and reused for all tests.
# This is safe because these are read-only bytes.

@pytest.fixture(scope="session")
def pdf_v1_bytes():
    """PDF bytes for the original policy."""
    return _make_pdf_bytes(POLICY_V1)


@pytest.fixture(scope="session")
def pdf_v2_bytes():
    """PDF bytes for the updated policy (two paragraphs changed)."""
    return _make_pdf_bytes(POLICY_V2)


# ── Fake Redis ────────────────────────────────────────────────────────────────
# fakeredis behaves exactly like real Redis but lives in memory.
# No Redis server needed. Each test gets a fresh empty instance.

@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)


# ── Fake embeddings ───────────────────────────────────────────────────────────
# Real embeddings would hit the OpenAI API on every test — slow and costs money.
# FakeEmbeddings returns small dummy vectors so ChromaDB works without any API call.

class FakeEmbeddings:
    """Returns 8-dimensional dummy vectors. Fast, free, no API key needed."""

    def embed_documents(self, texts):
        # return a slightly different vector per text so ChromaDB doesn't deduplicate
        return [[float((i + 1) % 9) / 9] * 8 for i, _ in enumerate(texts)]

    def embed_query(self, text):
        return [0.5] * 8


# ── Temp ChromaDB ─────────────────────────────────────────────────────────────
# Each test gets its own empty ChromaDB in a temporary directory.
# tmp_path is a built-in pytest fixture that creates a unique temp folder per test.

@pytest.fixture
def vectorstore(tmp_path):
    return Chroma(
        collection_name="test_policies",
        persist_directory=str(tmp_path / "chroma"),
        embedding_function=FakeEmbeddings(),
    )


# ── Combined env fixture ──────────────────────────────────────────────────────
# This patches Redis and ChromaDB in the ingest module.
# Every test that requests `ingest_env` gets:
#   - A fresh fake Redis
#   - A fresh temp ChromaDB
#   - Both injected into ingest/policies.py so it uses them instead of the real ones

@pytest.fixture
def ingest_env(fake_redis, vectorstore):
    """
    Patch the two external dependencies used by ingest/policies.py.

    `patch("ingest.policies.redis", fake_redis)` replaces the `redis` variable
    inside the policies module with our fake instance for the duration of the test.

    `patch("ingest.policies.get_vectorstore", return_value=vectorstore)` makes
    every call to get_vectorstore() return our temp ChromaDB instead of the real one.
    """
    with patch("ingest.policies.redis", fake_redis), \
         patch("ingest.policies.get_vectorstore", return_value=vectorstore):
        yield fake_redis, vectorstore


# ── Chat API fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def mock_vs():
    """MagicMock vectorstore with safe empty defaults."""
    vs = MagicMock()
    vs.similarity_search_with_relevance_scores.return_value = []
    vs.max_marginal_relevance_search.return_value = []
    vs._collection.get.return_value = {"ids": [], "metadatas": []}
    return vs


@pytest.fixture
def mock_llm():
    """MagicMock LLM whose invoke() returns a generic answer."""
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="Test answer.")
    return llm


@pytest.fixture
def app_client(fake_redis, mock_vs, mock_llm):
    """
    TestClient with all external I/O replaced:
      - Redis (memory nodes + ingest controller + rate limiter + lifespan)
      - ChromaDB vectorstore (retrieval node + ingest controller + lifespan)
      - LLM _get_chat() (generate_answer + summarize nodes)
    """
    with patch("graph.nodes.load_memory.redis", fake_redis), \
         patch("graph.nodes.store_memory.redis", fake_redis), \
         patch("graph.nodes.retrieve_context.get_vectorstore", return_value=mock_vs), \
         patch("graph.nodes.generate_answer._get_chat", return_value=mock_llm), \
         patch("graph.nodes.summarize._get_chat", return_value=mock_llm), \
         patch("middlewares.rate_limiter.get_redis", return_value=fake_redis), \
         patch("controllers.ingest_controller.redis", fake_redis), \
         patch("controllers.ingest_controller.get_vectorstore", return_value=mock_vs), \
         patch("main.get_redis", return_value=fake_redis), \
         patch("main.get_vectorstore", return_value=mock_vs):

        from main import app
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            yield client
