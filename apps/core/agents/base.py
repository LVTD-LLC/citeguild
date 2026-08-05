from dataclasses import dataclass

from django.conf import settings
from pydantic_ai.models.openrouter import OpenRouterModel

from apps.core.openrouter import build_openrouter_provider


@dataclass(frozen=True, slots=True)
class PydanticAIModelSpec:
    label: str  # e.g. "fast" or "smart"
    model_name: str | None = None  # OpenRouter model id override

    def build(self) -> OpenRouterModel:
        return build_model(label=self.label, model_name=self.model_name)


def build_model(*, label: str, model_name: str | None = None) -> OpenRouterModel:
    supported: dict[str, str] = settings.AI_MODELS
    selected_model = model_name or supported.get(label)
    if not selected_model:
        raise ValueError(f"Unsupported OpenRouter model label {label!r}.")

    return OpenRouterModel(selected_model, provider=build_openrouter_provider())
