from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Pydantic 会自动匹配大小写形式，例如 OPENAI_API_KEY 对应 openai_api_key。
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 环境变量优先于这里的默认值，例如 .env 中的 OPENAI_API_KEY 会覆盖空字符串。
    # 大语言模型
    llm_provider: str = "openai"
    llm_model: str = "deepseek-flash"
    openai_api_key: str = ""
    openai_api_base: str = "https://api.deepseek.com"
    anthropic_api_key: str = ""
    groq_api_key: str = ""

    # 嵌入模型
    embedding_provider: str = "huggingface"
    embedding_model: str = "bge-small-zh-v1.5"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_ttl_seconds: int = 86400  # 24 小时

    # 对话记忆
    # 最近消息保留 10 条（5 轮），待摘要消息达到 20 条（10 轮）时更新长期摘要。
    memory_recent_message_limit: int = 10
    summary_trigger_message_count: int = 20

    # 向量数据库
    chroma_persist_dir: str = "./chroma_db"
    chroma_collection: str = "policies"

    # 检索
    # 文本块只有达到该最低相似度（0.0～1.0）才会传给大模型。
    # 低于阈值的文本块会被丢弃；如果没有文本块通过，机器人会说明知识库中没有相关信息，
    # 避免模型根据弱相关内容产生幻觉。
    retrieval_score_threshold: float = 0.3

    # 文档导入
    max_file_size_mb: int = 50
    download_timeout_seconds: int = 30

    # 应用
    debug: bool = False
    log_level: str = "INFO"
    cors_origins: list[str] = ["*"]

# lru_cache 让 Settings 对象只创建一次，后续调用直接复用缓存对象。
@lru_cache
def get_settings() -> Settings:
    return Settings()
