"""Shared OpenRouter provider construction with CiteGuild attribution."""

from functools import lru_cache

from django.conf import settings
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

OPENROUTER_MODEL_PREFIX = "openrouter:"


@lru_cache(maxsize=1)
def _openrouter_provider(
    *,
    api_key: str,
    app_url: str,
    app_title: str,
) -> OpenRouterProvider:
    return OpenRouterProvider(
        api_key=api_key,
        app_url=app_url,
        app_title=app_title,
    )


def build_openrouter_provider() -> OpenRouterProvider:
    if not settings.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY must be set to build Pydantic AI models.")

    return _openrouter_provider(
        api_key=settings.OPENROUTER_API_KEY,
        app_url=settings.OPENROUTER_APP_URL,
        app_title=settings.OPENROUTER_APP_TITLE,
    )


def build_openrouter_embedding_model(model: str) -> OpenAIEmbeddingModel:
    if not model.startswith(OPENROUTER_MODEL_PREFIX):
        raise ValueError("Embedding model must use the openrouter provider.")

    model_name = model.removeprefix(OPENROUTER_MODEL_PREFIX)
    if not model_name:
        raise ValueError("OpenRouter embedding model id must not be empty.")

    return OpenAIEmbeddingModel(
        model_name,
        provider=build_openrouter_provider(),
    )
