from langchain.chat_models import init_chat_model

from config import get_settings


def get_llm(temperature: float = 0, max_tokens: int = 1000):
    setting = get_settings()
    provider = setting.llm_provider.lower()
    provider_kwargs = {
        "openai": {
            "api_key": setting.openai_api_key,
            "base_url": setting.openai_api_base,
        },
        "anthropic": {"api_key": setting.anthropic_api_key},
        "groq": {"api_key": setting.groq_api_key},
    }

    if provider not in provider_kwargs:
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")

    return init_chat_model(
        model=setting.llm_model,
        model_provider=provider,
        temperature=temperature,
        max_tokens=max_tokens,
        **provider_kwargs[provider],
    )
