import pytest

from apps.core.agents.base import build_model
from apps.core.openrouter import build_openrouter_embedding_model


def test_agent_model_attributes_openrouter_usage_to_configured_app(settings):
    settings.OPENROUTER_API_KEY = "openrouter-test-key"
    settings.OPENROUTER_APP_URL = "https://citeguild.lvtd.dev"
    settings.OPENROUTER_APP_TITLE = "CiteGuild"
    settings.AI_MODELS = {"fast": "openai/gpt-5-nano"}

    model = build_model(label="fast")

    headers = model._provider.client.default_headers
    assert headers["HTTP-Referer"] == "https://citeguild.lvtd.dev"
    assert headers["X-Title"] == "CiteGuild"


def test_embedding_model_rejects_non_openrouter_provider():
    with pytest.raises(ValueError, match="must use the openrouter provider"):
        build_openrouter_embedding_model("openai:text-embedding-3-small")
