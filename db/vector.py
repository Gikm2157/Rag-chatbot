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
        # cosine distance is the correct metric for text embeddings.
        # ChromaDB defaults to L2 which produces out-of-range relevance scores
        # (even negative) when used with LangChain's normalization formula.
        collection_metadata={"hnsw:space": "cosine"},
    )


# backward-compatible alias
def chroma() -> Chroma:
    return get_vectorstore()
