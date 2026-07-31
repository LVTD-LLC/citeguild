from dataclasses import dataclass
from functools import lru_cache

from django.conf import settings
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.openrouter import OpenRouterProvider


@dataclass(frozen=True, slots=True)
class PydanticAIModelSpec:
    label: str  # e.g. "fast" or "smart"
    model_name: str | None = None  # OpenRouter model id override

    def build(self) -> OpenRouterModel:
        return build_model(label=self.label, model_name=self.model_name)


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


def build_model(*, label: str, model_name: str | None = None) -> OpenRouterModel:
    supported: dict[str, str] = settings.AI_MODELS
    selected_model = model_name or supported.get(label)
    if not selected_model:
        raise ValueError(f"Unsupported OpenRouter model label {label!r}.")

    if not settings.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY must be set to build Pydantic AI models.")

    provider = _openrouter_provider(
        api_key=settings.OPENROUTER_API_KEY,
        app_url=settings.SITE_URL,
        app_title="CiteGuild",
    )
    return OpenRouterModel(selected_model, provider=provider)
