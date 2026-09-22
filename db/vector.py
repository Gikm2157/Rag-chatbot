from functools import lru_cache

from langchain_chroma import Chroma

from config import get_settings
from utils.embedding_adapter import get_embeddings


@lru_cache
def get_vectorstore() -> Chroma:
    setting = get_settings()
    return Chroma(
        collection_name=setting.chroma_collection,
        persist_directory=setting.chroma_persist_dir,
        embedding_function=get_embeddings(),
        # 文本嵌入使用余弦距离。ChromaDB 默认的 L2 距离经过 LangChain 归一化后，
        # 可能产生超出正常范围甚至为负数的相关度分数。
        collection_metadata={"hnsw:space": "cosine"},
    )


# 为旧调用方式保留的兼容别名。
def chroma() -> Chroma:
    return get_vectorstore()
