import socket
from collections.abc import Mapping
from contextlib import contextmanager

import pytest

from apps.core.safe_fetch import (
    SafeFetchClient,
    SafeFetchError,
    SafeFetchErrorCode,
    TransportResponse,
    resolve_public_addresses,
)


class FakeResponse:
    def __init__(self, *, status=200, headers=None, chunks=()):
        self.status = status
        self.headers = {key.lower(): value for key, value in (headers or {}).items()}
        self.chunks = list(chunks)
        self.closed = False
        self.timeouts = []

    def read(self, amount):
        if not self.chunks:
            return b""
        chunk = self.chunks.pop(0)
        if len(chunk) <= amount:
            return chunk
        self.chunks.insert(0, chunk[amount:])
        return chunk[:amount]

    def close(self):
        self.closed = True

    def set_timeout(self, timeout_seconds):
        self.timeouts.append(timeout_seconds)


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.targets = []
        self.headers = []

    def __call__(self, target, headers, timeout_seconds):
        self.targets.append(target)
        self.headers.append(headers)
        return self.responses.pop(0)


def resolver_for(mapping: Mapping[str, tuple[str, ...]]):
    def resolve(hostname, port):
        del port
        return mapping[hostname]

    return resolve


@pytest.mark.parametrize(
    "address",
    [
        "0.0.0.0",
        "10.0.0.1",
        "100.64.0.1",
        "127.0.0.1",
        "169.254.169.254",
        "172.16.0.1",
        "192.168.1.1",
        "224.0.0.1",
        "240.0.0.1",
        "::",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
def test_resolver_blocks_every_non_global_address(monkeypatch, address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(family, socket.SOCK_STREAM, 6, "", (address, 443))],
    )

    with pytest.raises(SafeFetchError) as error:
        resolve_public_addresses("attacker.example", 443)

    assert error.value.code == SafeFetchErrorCode.BLOCKED_ADDRESS
    assert address not in str(error.value)


def test_resolver_rejects_mixed_public_and_private_dns_answers(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ],
    )

    with pytest.raises(SafeFetchError) as error:
        resolve_public_addresses("mixed.example", 443)

    assert error.value.code == SafeFetchErrorCode.BLOCKED_ADDRESS


def test_fetch_pins_connection_to_validated_ip_and_preserves_tls_hostname():
    response = FakeResponse(
        headers={
            "Content-Type": "application/xml",
            "Content-Language": "en-US",
            "X-Robots-Tag": "noindex",
            "Set-Cookie": "private=session-value",
        },
        chunks=[b"<urlset />"],
    )
    transport = FakeTransport([response])
    client = SafeFetchClient(
        resolver=resolver_for({"example.com": ("93.184.216.34",)}),
        transport=transport,
    )

    result = client.fetch(
        "https://example.com/sitemap.xml?part=1",
        max_bytes=1_000,
        allowed_content_types={"application/xml"},
    )

    target = transport.targets[0]
    assert target.ip_address == "93.184.216.34"
    assert target.hostname == "example.com"
    assert target.server_hostname == "example.com"
    assert target.request_target == "/sitemap.xml?part=1"
    assert transport.headers[0]["Host"] == "example.com"
    assert transport.headers[0]["User-Agent"].startswith("CiteGuildBot/")
    assert result.body == b"<urlset />"
    assert result.headers == {
        "content-language": "en-US",
        "x-robots-tag": "noindex",
    }
    assert "session-value" not in repr(result)
    assert response.closed is True


@pytest.mark.parametrize(
    ("url", "expected_code"),
    [
        ("file:///etc/passwd", SafeFetchErrorCode.INVALID_URL),
        ("ftp://example.com/file", SafeFetchErrorCode.INVALID_URL),
        ("https://user:password@example.com/", SafeFetchErrorCode.INVALID_URL),
        ("https://example.com:8443/", SafeFetchErrorCode.BLOCKED_PORT),
        ("http://example.com:443/", SafeFetchErrorCode.BLOCKED_PORT),
        ("https://example.com/%0d%0aX-Test:yes", SafeFetchErrorCode.INVALID_URL),
    ],
)
def test_fetch_rejects_unsafe_url_shapes_before_transport(url, expected_code):
    transport = FakeTransport([])
    client = SafeFetchClient(
        resolver=resolver_for({"example.com": ("93.184.216.34",)}),
        transport=transport,
    )

    with pytest.raises(SafeFetchError) as error:
        client.fetch(url, max_bytes=100, allowed_content_types={"text/html"})

    assert error.value.code == expected_code
    assert not transport.targets


def test_fetch_blocks_metadata_hostname_even_if_dns_claims_it_is_public():
    transport = FakeTransport([])
    client = SafeFetchClient(
        resolver=resolver_for({"metadata.google.internal": ("93.184.216.34",)}),
        transport=transport,
    )

    with pytest.raises(SafeFetchError) as error:
        client.fetch(
            "http://metadata.google.internal/computeMetadata/v1/",
            max_bytes=100,
            allowed_content_types={"text/plain"},
        )

    assert error.value.code == SafeFetchErrorCode.BLOCKED_ADDRESS
    assert not transport.targets


def test_fetch_revalidates_every_injected_resolver_address_before_transport():
    transport = FakeTransport([])
    client = SafeFetchClient(
        resolver=resolver_for({"attacker.example": ("127.0.0.1",)}),
        transport=transport,
    )

    with pytest.raises(SafeFetchError) as error:
        client.fetch(
            "https://attacker.example/",
            max_bytes=100,
            allowed_content_types={"text/html"},
        )

    assert error.value.code == SafeFetchErrorCode.BLOCKED_ADDRESS
    assert not transport.targets


def test_every_redirect_is_resolved_validated_and_pinned_again():
    first = FakeResponse(status=302, headers={"Location": "https://second.example/map.xml"})
    second = FakeResponse(headers={"Content-Type": "application/xml"}, chunks=[b"ok"])
    transport = FakeTransport([first, second])
    client = SafeFetchClient(
        resolver=resolver_for(
            {
                "first.example": ("93.184.216.34",),
                "second.example": ("142.250.72.14",),
            }
        ),
        transport=transport,
    )

    result = client.fetch(
        "https://first.example/map.xml",
        max_bytes=100,
        allowed_content_types={"application/xml"},
    )

    assert [target.ip_address for target in transport.targets] == [
        "93.184.216.34",
        "142.250.72.14",
    ]
    assert result.redirect_count == 1
    assert first.closed is True


def test_redirect_to_private_target_is_blocked_before_second_request():
    transport = FakeTransport(
        [FakeResponse(status=302, headers={"Location": "http://127.0.0.1/admin"})]
    )
    client = SafeFetchClient(
        resolver=resolver_for({"public.example": ("93.184.216.34",)}),
        transport=transport,
    )

    with pytest.raises(SafeFetchError) as error:
        client.fetch(
            "https://public.example/map.xml",
            max_bytes=100,
            allowed_content_types={"application/xml"},
        )

    assert error.value.code == SafeFetchErrorCode.BLOCKED_ADDRESS
    assert len(transport.targets) == 1


def test_redirect_limit_stops_loops():
    transport = FakeTransport(
        [
            FakeResponse(status=302, headers={"Location": "/two"}),
            FakeResponse(status=302, headers={"Location": "/three"}),
        ]
    )
    client = SafeFetchClient(
        max_redirects=1,
        resolver=resolver_for({"example.com": ("93.184.216.34",)}),
        transport=transport,
    )

    with pytest.raises(SafeFetchError) as error:
        client.fetch(
            "https://example.com/one",
            max_bytes=100,
            allowed_content_types={"text/html"},
        )

    assert error.value.code == SafeFetchErrorCode.TOO_MANY_REDIRECTS


def test_body_limit_applies_to_streamed_plain_content():
    transport = FakeTransport(
        [FakeResponse(headers={"Content-Type": "text/html"}, chunks=[b"12345", b"67890"])]
    )
    client = SafeFetchClient(
        resolver=resolver_for({"example.com": ("93.184.216.34",)}),
        transport=transport,
    )

    with pytest.raises(SafeFetchError) as error:
        client.fetch(
            "https://example.com/",
            max_bytes=8,
            allowed_content_types={"text/html"},
        )

    assert error.value.code == SafeFetchErrorCode.BODY_TOO_LARGE


def test_body_limit_applies_after_gzip_decompression():
    import gzip

    compressed = gzip.compress(b"a" * 10_000)
    transport = FakeTransport(
        [
            FakeResponse(
                headers={"Content-Type": "application/xml", "Content-Encoding": "gzip"},
                chunks=[compressed],
            )
        ]
    )
    client = SafeFetchClient(
        resolver=resolver_for({"example.com": ("93.184.216.34",)}),
        transport=transport,
    )

    with pytest.raises(SafeFetchError) as error:
        client.fetch(
            "https://example.com/sitemap.xml",
            max_bytes=1_000,
            allowed_content_types={"application/xml"},
        )

    assert error.value.code == SafeFetchErrorCode.BODY_TOO_LARGE


def test_content_type_and_encoding_are_allowlisted():
    transport = FakeTransport([FakeResponse(headers={"Content-Type": "application/octet-stream"})])
    client = SafeFetchClient(
        resolver=resolver_for({"example.com": ("93.184.216.34",)}),
        transport=transport,
    )

    with pytest.raises(SafeFetchError) as error:
        client.fetch(
            "https://example.com/file",
            max_bytes=100,
            allowed_content_types={"application/xml"},
        )

    assert error.value.code == SafeFetchErrorCode.UNSUPPORTED_CONTENT_TYPE


def test_unsupported_content_encoding_is_rejected_without_reading_body():
    response = FakeResponse(
        headers={"Content-Type": "text/html", "Content-Encoding": "br"},
        chunks=[b"secret body"],
    )
    client = SafeFetchClient(
        resolver=resolver_for({"example.com": ("93.184.216.34",)}),
        transport=FakeTransport([response]),
    )

    with pytest.raises(SafeFetchError) as error:
        client.fetch(
            "https://example.com/",
            max_bytes=100,
            allowed_content_types={"text/html"},
        )

    assert error.value.code == SafeFetchErrorCode.UNSUPPORTED_CONTENT_ENCODING
    assert response.chunks == [b"secret body"]


def test_content_length_limit_rejects_response_without_reading_body():
    response = FakeResponse(
        headers={"Content-Type": "text/html", "Content-Length": "101"},
        chunks=[b"secret body"],
    )
    client = SafeFetchClient(
        resolver=resolver_for({"example.com": ("93.184.216.34",)}),
        transport=FakeTransport([response]),
    )

    with pytest.raises(SafeFetchError) as error:
        client.fetch(
            "https://example.com/",
            max_bytes=100,
            allowed_content_types={"text/html"},
        )

    assert error.value.code == SafeFetchErrorCode.BODY_TOO_LARGE
    assert response.chunks == [b"secret body"]


@pytest.mark.parametrize(
    ("status", "expected_code", "retryable"),
    [
        (429, SafeFetchErrorCode.TEMPORARY_FAILURE, True),
        (503, SafeFetchErrorCode.TEMPORARY_FAILURE, True),
        (404, SafeFetchErrorCode.HTTP_ERROR, False),
    ],
)
def test_http_errors_are_safely_categorized(status, expected_code, retryable):
    transport = FakeTransport([FakeResponse(status=status)])
    client = SafeFetchClient(
        resolver=resolver_for({"example.com": ("93.184.216.34",)}),
        transport=transport,
    )

    with pytest.raises(SafeFetchError) as error:
        client.fetch(
            "https://example.com/private?token=secret",
            max_bytes=100,
            allowed_content_types={"text/html"},
        )

    assert error.value.code == expected_code
    assert error.value.retryable is retryable
    assert "secret" not in str(error.value)


def test_transport_timeout_is_retryable_and_does_not_leak_url():
    def timeout_transport(target, headers, timeout_seconds):
        del target, headers, timeout_seconds
        raise TimeoutError("upstream https://example.com/?token=secret timed out")

    client = SafeFetchClient(
        resolver=resolver_for({"example.com": ("93.184.216.34",)}),
        transport=timeout_transport,
    )

    with pytest.raises(SafeFetchError) as error:
        client.fetch(
            "https://example.com/?token=secret",
            max_bytes=100,
            allowed_content_types={"text/html"},
        )

    assert error.value.code == SafeFetchErrorCode.TIMEOUT
    assert error.value.retryable is True
    assert "secret" not in str(error.value)


def test_stream_timeout_is_retryable_and_response_is_closed():
    class SlowResponse(FakeResponse):
        def read(self, amount):
            del amount
            raise TimeoutError("raw upstream details")

    response = SlowResponse(headers={"Content-Type": "text/html"})
    client = SafeFetchClient(
        resolver=resolver_for({"example.com": ("93.184.216.34",)}),
        transport=FakeTransport([response]),
    )

    with pytest.raises(SafeFetchError) as error:
        client.fetch(
            "https://example.com/slow",
            max_bytes=100,
            allowed_content_types={"text/html"},
        )

    assert error.value.code == SafeFetchErrorCode.TIMEOUT
    assert error.value.retryable is True
    assert response.timeouts
    assert response.closed is True


def test_per_host_concurrency_slot_is_held_while_streaming_body():
    class RecordingLimiter:
        active = False

        @contextmanager
        def acquire(self, hostname, *, timeout_seconds):
            del hostname, timeout_seconds
            self.active = True
            try:
                yield
            finally:
                self.active = False

    limiter = RecordingLimiter()

    class AssertingResponse(FakeResponse):
        def read(self, amount):
            assert limiter.active is True
            return super().read(amount)

    client = SafeFetchClient(
        resolver=resolver_for({"example.com": ("93.184.216.34",)}),
        transport=FakeTransport(
            [AssertingResponse(headers={"Content-Type": "text/html"}, chunks=[b"ok"])]
        ),
    )
    client.rate_limiter = limiter

    result = client.fetch(
        "https://example.com/",
        max_bytes=100,
        allowed_content_types={"text/html"},
    )

    assert result.body == b"ok"
    assert limiter.active is False


def test_transport_response_protocol_remains_minimal():
    assert set(TransportResponse.__annotations__) == {"status", "headers"}
