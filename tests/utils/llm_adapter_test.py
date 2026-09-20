from types import SimpleNamespace
from unittest.mock import patch

import pytest

from utils.llm_adapter import get_llm


def _settings(provider: str):
    return SimpleNamespace(
        llm_provider=provider,
        llm_model="test-model",
        openai_api_key="openai-key",
        openai_api_base="https://example.com/v1",
        anthropic_api_key="anthropic-key",
        groq_api_key="groq-key",
    )


@pytest.mark.parametrize(
    ("provider", "expected_provider_kwargs"),
    [
        (
            "openai",
            {
                "api_key": "openai-key",
                "base_url": "https://example.com/v1",
            },
        ),
        ("anthropic", {"api_key": "anthropic-key"}),
        ("groq", {"api_key": "groq-key"}),
    ],
)
def test_get_llm_uses_unified_model_factory(provider, expected_provider_kwargs):
    with (
        patch("utils.llm_adapter.get_settings", return_value=_settings(provider)),
        patch("utils.llm_adapter.init_chat_model") as init_model,
    ):
        get_llm(temperature=0.2, max_tokens=321)

    init_model.assert_called_once_with(
        model="test-model",
        model_provider=provider,
        temperature=0.2,
        max_tokens=321,
        **expected_provider_kwargs,
    )


def test_get_llm_rejects_unsupported_provider():
    with patch(
        "utils.llm_adapter.get_settings",
        return_value=_settings("unsupported"),
    ):
        with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER: unsupported"):
            get_llm()
