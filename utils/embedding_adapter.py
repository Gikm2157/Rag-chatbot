from functools import lru_cache

from config import get_settings


@lru_cache
def get_embeddings():
    setting = get_settings()
    provider = setting.embedding_provider.lower()
    model = setting.embedding_model

    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model=model)

    elif provider == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(model_name=model)

    else:
        raise ValueError(f"Unsupported EMBEDDING_PROVIDER: {provider}")
