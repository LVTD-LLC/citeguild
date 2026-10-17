"""Exercise provider failures through the real SDK, without network calls."""

import asyncio

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic_ai import Embedder
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.providers.openai import OpenAIProvider

from apps.core.article_embeddings import EmbeddingError, PydanticEmbeddingClient


@pytest.fixture
def transport_client():
    clients = []

    def build(handler):
        sdk = AsyncOpenAI(
            api_key="test-only",
            base_url="https://provider.example/v1",
            max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        clients.append(sdk)
        client = PydanticEmbeddingClient.__new__(PydanticEmbeddingClient)
        client.embedder = Embedder(
            OpenAIEmbeddingModel("test-model", provider=OpenAIProvider(openai_client=sdk))
        )
        return client

    yield build
    for sdk in clients:
        asyncio.run(sdk.close())


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.ConnectError])
def test_sdk_transport_failure_remains_retryable(transport_client, failure):
    calls = []

    def fail(request):
        calls.append(request.url.path)
        raise failure("test transport failure", request=request)

    client = transport_client(fail)
    with pytest.raises(EmbeddingError) as raised:
        client.embed("Synthetic transport test", dimensions=2)

    assert raised.value.code == "provider_unavailable"
    assert raised.value.retryable is True
    assert str(raised.value) == "provider_unavailable"
    assert calls == ["/v1/embeddings"]


@pytest.mark.parametrize("status,retryable", [(400, False), (401, False), (429, True), (503, True)])
def test_sdk_http_errors_keep_existing_retry_policy(transport_client, status, retryable):
    client = transport_client(
        lambda request: httpx.Response(status, json={"error": {"message": "synthetic error"}})
    )
    with pytest.raises(EmbeddingError) as raised:
        client.embed("Synthetic transport test", dimensions=2)

    assert (raised.value.code, raised.value.retryable) == ("provider_http_error", retryable)
    assert str(raised.value) == "provider_http_error"


def test_sdk_success_preserves_vector_and_usage(transport_client):
    client = transport_client(
        lambda request: httpx.Response(
            200,
            json={
                "object": "list",
                "model": "test-model",
                "data": [{"object": "embedding", "index": 0, "embedding": [0.1, 0.2]}],
                "usage": {"prompt_tokens": 3, "total_tokens": 3},
            },
        )
    )
    result = client.embed("Synthetic transport test", dimensions=2)
    assert result.vector == [0.1, 0.2]
    assert result.input_tokens == 3


def test_unknown_model_api_failure_is_not_retried():
    class FailedEmbedder:
        def embed_documents_sync(self, text, *, settings):
            raise ModelAPIError("test-model", "synthetic non-transport failure")

    client = PydanticEmbeddingClient.__new__(PydanticEmbeddingClient)
    client.embedder = FailedEmbedder()
    with pytest.raises(EmbeddingError) as raised:
        client.embed("Synthetic transport test", dimensions=2)

    assert (raised.value.code, raised.value.retryable) == ("provider_error", False)
    assert str(raised.value) == "provider_error"
