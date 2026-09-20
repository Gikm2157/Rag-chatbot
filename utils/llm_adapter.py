from config import get_settings


def get_llm(temperature: float = 0, max_tokens: int = 1000):
    setting = get_settings()
    provider = setting.llm_provider.lower()
    model = setting.llm_model

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model,
            api_key=setting.openai_api_key,
            base_url=setting.openai_api_base,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, temperature=temperature, max_tokens=max_tokens)

    elif provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=model, temperature=temperature, max_tokens=max_tokens)

    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")
