"""
conftest.py：所有测试共用的夹具。

pytest 会在运行测试前自动加载此文件；这里定义的夹具无需导入，所有测试文件均可使用。
"""

import pytest
import fakeredis
from fpdf import FPDF
from unittest.mock import MagicMock, patch
from langchain_chroma import Chroma


# ── 测试文档内容 ──────────────────────────────────────────────────────────────
# 同一政策的两个版本。V2 修改了两个段落（退货期 30→60 天，退款时间 5～7→3～5 天），
# 其他段落完全相同，因此差异更新只能处理发生变化的文本块。
# 文档长度足以在 chunk_size=800 时产生多个文本块。

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

# 已变化：退货期限（30→60 天）、退款时间（5～7→3～5 天）
# 未变化：换货政策、配送政策、隐私政策
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
    """使用纯文本生成真实 PDF 并返回字节；fpdf2 无需依赖外部工具。"""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for paragraph in text.strip().split("\n\n"):
        pdf.multi_cell(0, 8, paragraph.strip())
        pdf.ln(4)
    return bytes(pdf.output())


# ── PDF 夹具 ─────────────────────────────────────────────────────────────────
# scope="session" 表示 PDF 字节只生成一次并由所有测试复用；只读数据可以安全复用。

@pytest.fixture(scope="session")
def pdf_v1_bytes():
    """原始政策 PDF 的字节数据。"""
    return _make_pdf_bytes(POLICY_V1)


@pytest.fixture(scope="session")
def pdf_v2_bytes():
    """更新后政策 PDF 的字节数据，其中两个段落发生了变化。"""
    return _make_pdf_bytes(POLICY_V2)


# ── 模拟 Redis ────────────────────────────────────────────────────────────────
# fakeredis 的行为与真实 Redis 相同，但数据只保存在内存中，无需启动 Redis 服务。
# 每个测试都会获得一个全新的空实例。

@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)


# ── 模拟嵌入模型 ─────────────────────────────────────────────────────────────
# 真实嵌入模型会让每次测试都调用外部 API，速度慢且产生费用。
# FakeEmbeddings 返回小型模拟向量，让 ChromaDB 无需 API 即可工作。

class FakeEmbeddings:
    """返回 8 维模拟向量，速度快、无费用，也不需要 API Key。"""

    def embed_documents(self, texts):
        # 为每段文本返回略有差异的向量，防止 ChromaDB 将其去重。
        return [[float((i + 1) % 9) / 9] * 8 for i, _ in enumerate(texts)]

    def embed_query(self, text):
        return [0.5] * 8


# ── 临时 ChromaDB ────────────────────────────────────────────────────────────
# 每个测试都在独立临时目录中使用空 ChromaDB。tmp_path 是 pytest 内置夹具，
# 会为每个测试创建唯一的临时文件夹。

@pytest.fixture
def vectorstore(tmp_path):
    return Chroma(
        collection_name="test_policies",
        persist_directory=str(tmp_path / "chroma"),
        embedding_function=FakeEmbeddings(),
    )


# ── 组合环境夹具 ──────────────────────────────────────────────────────────────
# 替换导入模块中的 Redis 和 ChromaDB。每个使用 ingest_env 的测试都会获得：
#   - 一个全新的模拟 Redis
#   - 一个全新的临时 ChromaDB
#   - 注入 ingest/policies.py 的上述实例，用来替代真实外部服务

@pytest.fixture
def ingest_env(fake_redis, vectorstore):
    """
    替换 ingest/policies.py 使用的两个外部依赖。

    第一个 patch 在测试期间将 policies 模块的 redis 变量替换为模拟实例；
    第二个 patch 让 get_vectorstore() 始终返回临时 ChromaDB，而不连接真实数据库。
    """
    with patch("ingest.policies.redis", fake_redis), \
         patch("ingest.policies.get_vectorstore", return_value=vectorstore):
        yield fake_redis, vectorstore


# ── 聊天 API 夹具 ────────────────────────────────────────────────────────────

@pytest.fixture
def mock_vs():
    """带有安全空默认值的 MagicMock 向量库。"""
    vs = MagicMock()
    vs.similarity_search_with_relevance_scores.return_value = []
    vs.max_marginal_relevance_search.return_value = []
    vs._collection.get.return_value = {"ids": [], "metadatas": []}
    return vs


@pytest.fixture
def mock_llm():
    """invoke() 返回通用答案的 MagicMock 大模型。"""
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="Test answer.")
    return llm


@pytest.fixture
def app_client(fake_redis, mock_vs, mock_llm):
    """
    替换所有外部 I/O 的 TestClient：
      - Redis（记忆节点、导入控制器、限流器和生命周期）
      - ChromaDB（检索节点、导入控制器和生命周期）
      - 大模型 _get_chat()（回答生成和摘要节点）
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
