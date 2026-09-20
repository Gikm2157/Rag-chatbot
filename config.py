from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Pydantic automatically matches ex:- OPENAI_API_KEY become openai_api_key
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # take env value if defined or use the default value defined here, for example, if you have OPENAI_API_KEY in your .env file, it will override the default empty string value defined here.
    # LLM
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    openai_api_base: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    groq_api_key: str = ""

    # Embeddings
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_ttl_seconds: int = 86400  # 24 hours

    # Vector DB
    chroma_persist_dir: str = "./chroma_db"
    chroma_collection: str = "policies"

    # Retrieval
    # Minimum similarity score (0.0–1.0) a chunk must reach to be passed to the LLM.
    # Chunks below this score are discarded — if none pass, the bot replies with
    # "I don't have information about that" instead of hallucinating from weak matches.
    retrieval_score_threshold: float = 0.3

    # Ingest
    max_file_size_mb: int = 50
    download_timeout_seconds: int = 30

    # App
    debug: bool = False
    log_level: str = "INFO"
    cors_origins: list[str] = ["*"]

# What lru_cache does
# It means:
# “Create Settings object only ONCE, then reuse it forever.”
@lru_cache
def get_settings() -> Settings:
    return Settings()
