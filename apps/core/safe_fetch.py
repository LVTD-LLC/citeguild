"""SSRF-safe, resource-bounded HTTP transport for crawler-controlled fetches."""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import threading
import time
import zlib
from collections.abc import Callable, Iterator, Mapping, Set
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from urllib.parse import quote, unquote_to_bytes, urljoin, urlsplit, urlunsplit


class SafeFetchErrorCode(StrEnum):
    INVALID_URL = "invalid_url"
    BLOCKED_ADDRESS = "blocked_address"
    BLOCKED_PORT = "blocked_port"
    DNS_FAILURE = "dns_failure"
    TIMEOUT = "timeout"
    UNREACHABLE = "unreachable"
    TLS_ERROR = "tls_error"
    TOO_MANY_REDIRECTS = "too_many_redirects"
    BODY_TOO_LARGE = "body_too_large"
    UNSUPPORTED_CONTENT_TYPE = "unsupported_content_type"
    UNSUPPORTED_CONTENT_ENCODING = "unsupported_content_encoding"
    INVALID_CONTENT_ENCODING = "invalid_content_encoding"
    TEMPORARY_FAILURE = "temporary_failure"
    HTTP_ERROR = "http_error"
    CONCURRENCY_LIMIT = "concurrency_limit"


_SAFE_ERROR_MESSAGES = {
    SafeFetchErrorCode.INVALID_URL: "The URL is invalid or unsupported.",
    SafeFetchErrorCode.BLOCKED_ADDRESS: "The destination is not publicly routable.",
    SafeFetchErrorCode.BLOCKED_PORT: "The destination port is not allowed.",
    SafeFetchErrorCode.DNS_FAILURE: "The destination hostname could not be resolved.",
    SafeFetchErrorCode.TIMEOUT: "The destination timed out.",
    SafeFetchErrorCode.UNREACHABLE: "The destination could not be reached.",
    SafeFetchErrorCode.TLS_ERROR: "The destination failed TLS verification.",
    SafeFetchErrorCode.TOO_MANY_REDIRECTS: "The destination redirected too many times.",
    SafeFetchErrorCode.BODY_TOO_LARGE: "The response exceeded the allowed size.",
    SafeFetchErrorCode.UNSUPPORTED_CONTENT_TYPE: "The response content type is not allowed.",
    SafeFetchErrorCode.UNSUPPORTED_CONTENT_ENCODING: (
        "The response content encoding is not supported."
    ),
    SafeFetchErrorCode.INVALID_CONTENT_ENCODING: "The response encoding is invalid.",
    SafeFetchErrorCode.TEMPORARY_FAILURE: "The destination returned a temporary error.",
    SafeFetchErrorCode.HTTP_ERROR: "The destination returned an HTTP error.",
    SafeFetchErrorCode.CONCURRENCY_LIMIT: "The destination is currently rate limited.",
}


class SafeFetchError(Exception):
    """A typed, deliberately sanitized crawler failure."""

    def __init__(self, code: SafeFetchErrorCode, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(_SAFE_ERROR_MESSAGES[code])


@dataclass(frozen=True, slots=True)
class PinnedTarget:
    scheme: str
    hostname: str
    server_hostname: str
    ip_address: str
    port: int
    request_target: str
    normalized_url: str


class TransportResponse(Protocol):
    status: int
    headers: Mapping[str, str]

    def read(self, amount: int) -> bytes: ...

    def set_timeout(self, timeout_seconds: float) -> None: ...

    def close(self) -> None: ...


Transport = Callable[[PinnedTarget, Mapping[str, str], float], TransportResponse]
# Resolver implementations are injectable, so their output is always untrusted.
Resolver = Callable[[str, int], tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class SafeFetchResult:
    body: bytes
    content_type: str
    final_url: str
    status: int
    redirect_count: int


def _blocked_address() -> SafeFetchError:
    return SafeFetchError(SafeFetchErrorCode.BLOCKED_ADDRESS)


def _validate_address(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise SafeFetchError(SafeFetchErrorCode.DNS_FAILURE, retryable=True) from error
    if (
        not address.is_global
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_private
        or address.is_reserved
        or address.is_unspecified
    ):
        raise _blocked_address()
    return address.compressed


def resolve_public_addresses(hostname: str, port: int) -> tuple[str, ...]:
    """Resolve once and reject the entire answer if any address is non-public."""
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        return (_validate_address(str(literal)),)

    try:
        answers = socket.getaddrinfo(
            hostname,
            port,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except (socket.gaierror, OSError) as error:
        raise SafeFetchError(SafeFetchErrorCode.DNS_FAILURE, retryable=True) from error

    addresses = tuple(dict.fromkeys(answer[4][0] for answer in answers))
    if not addresses:
        raise SafeFetchError(SafeFetchErrorCode.DNS_FAILURE, retryable=True)
    return tuple(_validate_address(address) for address in addresses)


_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata.aws.internal",
        "metadata.google.internal",
        "metadata.azure.internal",
    }
)


def _contains_control_characters(value: str) -> bool:
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return True
    try:
        decoded = unquote_to_bytes(value)
    except ValueError:
        return True
    return any(byte < 32 or byte == 127 for byte in decoded)


def _normalized_hostname(raw_hostname: str) -> str:
    try:
        hostname = raw_hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise SafeFetchError(SafeFetchErrorCode.INVALID_URL) from error
    if not hostname:
        raise SafeFetchError(SafeFetchErrorCode.INVALID_URL)
    if (
        hostname in _BLOCKED_HOSTNAMES
        or hostname.endswith(".localhost")
        or hostname.endswith(".internal")
    ):
        raise _blocked_address()
    return hostname


def _format_host(hostname: str, port: int, scheme: str) -> str:
    display_hostname = f"[{hostname}]" if ":" in hostname else hostname
    default_port = 443 if scheme == "https" else 80
    return display_hostname if port == default_port else f"{display_hostname}:{port}"


def _request_target(path: str, query: str) -> str:
    encoded_path = quote(path or "/", safe="/%:@!$&'()*+,;=-._~")
    encoded_query = quote(query, safe="/%?:@!$&'()*+,;=-._~")
    return f"{encoded_path}?{encoded_query}" if encoded_query else encoded_path


def _build_target(url: str, resolver: Resolver) -> PinnedTarget:
    if not isinstance(url, str) or _contains_control_characters(url):
        raise SafeFetchError(SafeFetchErrorCode.INVALID_URL)
    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        raw_hostname = parsed.hostname
        parsed_port = parsed.port
    except ValueError as error:
        raise SafeFetchError(SafeFetchErrorCode.INVALID_URL) from error
    if scheme not in {"http", "https"} or not raw_hostname:
        raise SafeFetchError(SafeFetchErrorCode.INVALID_URL)
    if parsed.username or parsed.password:
        raise SafeFetchError(SafeFetchErrorCode.INVALID_URL)

    hostname = _normalized_hostname(raw_hostname)
    expected_port = 443 if scheme == "https" else 80
    port = parsed_port or expected_port
    if port != expected_port:
        raise SafeFetchError(SafeFetchErrorCode.BLOCKED_PORT)

    try:
        literal_address = ipaddress.ip_address(hostname)
    except ValueError:
        addresses = resolver(hostname, port)
    else:
        addresses = (_validate_address(str(literal_address)),)
    # Keep validation at this socket-boundary even when the default resolver also
    # validates. Alternate resolvers must never be able to bypass SSRF controls.
    validated_addresses = tuple(_validate_address(address) for address in addresses)
    if not validated_addresses:
        raise SafeFetchError(SafeFetchErrorCode.DNS_FAILURE, retryable=True)
    host = _format_host(hostname, port, scheme)
    target = _request_target(parsed.path, parsed.query)
    normalized_url = urlunsplit((scheme, host, parsed.path or "/", parsed.query, ""))
    return PinnedTarget(
        scheme=scheme,
        hostname=hostname,
        server_hostname=hostname,
        ip_address=validated_addresses[0],
        port=port,
        request_target=target,
        normalized_url=normalized_url,
    )


class _PinnedHTTPResponse:
    def __init__(self, response: http.client.HTTPResponse, connection_socket: socket.socket):
        self._response = response
        self._socket = connection_socket
        self.status = response.status
        self.headers = {key.lower(): value for key, value in response.headers.items()}

    def read(self, amount: int) -> bytes:
        return self._response.read(amount)

    def set_timeout(self, timeout_seconds: float) -> None:
        self._socket.settimeout(timeout_seconds)

    def close(self) -> None:
        try:
            self._response.close()
        finally:
            self._socket.close()


def _default_transport(
    target: PinnedTarget, headers: Mapping[str, str], timeout_seconds: float
) -> TransportResponse:
    connection_socket = socket.create_connection(
        (target.ip_address, target.port),
        timeout=timeout_seconds,
    )
    try:
        connection_socket.settimeout(timeout_seconds)
        if target.scheme == "https":
            context = ssl.create_default_context()
            connection_socket = context.wrap_socket(
                connection_socket,
                server_hostname=target.server_hostname,
            )

        request_lines = [f"GET {target.request_target} HTTP/1.1"]
        request_lines.extend(f"{name}: {value}" for name, value in headers.items())
        request_lines.append("Connection: close")
        payload = ("\r\n".join(request_lines) + "\r\n\r\n").encode("ascii")
        connection_socket.sendall(payload)
        response = http.client.HTTPResponse(connection_socket, method="GET")
        response.begin()
        return _PinnedHTTPResponse(response, connection_socket)
    except Exception:
        connection_socket.close()
        raise


@dataclass(slots=True)
class _DomainState:
    semaphore: threading.BoundedSemaphore
    timing_lock: threading.Lock
    last_started_at: float = 0.0


class DomainRateLimiter:
    """A bounded, process-local per-host concurrency and pacing guard."""

    def __init__(
        self,
        *,
        concurrency: int,
        minimum_interval_seconds: float,
        max_tracked_hosts: int = 1_024,
    ):
        self.concurrency = max(1, concurrency)
        self.minimum_interval_seconds = max(0.0, minimum_interval_seconds)
        self.max_tracked_hosts = max(1, max_tracked_hosts)
        self._states: dict[str, _DomainState] = {}
        self._states_lock = threading.Lock()
        self._overflow = self._new_state()

    def _new_state(self) -> _DomainState:
        return _DomainState(
            semaphore=threading.BoundedSemaphore(self.concurrency),
            timing_lock=threading.Lock(),
        )

    def _state_for(self, hostname: str) -> _DomainState:
        with self._states_lock:
            state = self._states.get(hostname)
            if state is not None:
                return state
            if len(self._states) >= self.max_tracked_hosts:
                return self._overflow
            state = self._new_state()
            self._states[hostname] = state
            return state

    @contextmanager
    def acquire(self, hostname: str, *, timeout_seconds: float) -> Iterator[None]:
        state = self._state_for(hostname)
        if not state.semaphore.acquire(timeout=timeout_seconds):
            raise SafeFetchError(SafeFetchErrorCode.CONCURRENCY_LIMIT, retryable=True)
        try:
            with state.timing_lock:
                wait_seconds = self.minimum_interval_seconds - (
                    time.monotonic() - state.last_started_at
                )
                if wait_seconds > 0:
                    time.sleep(wait_seconds)
                state.last_started_at = time.monotonic()
            yield
        finally:
            state.semaphore.release()


def _header_value(headers: Mapping[str, str], name: str) -> str:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value.strip()
    return ""


def _raise_too_large() -> None:
    raise SafeFetchError(SafeFetchErrorCode.BODY_TOO_LARGE)


def _set_remaining_timeout(response: TransportResponse, deadline: float) -> None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    response.set_timeout(remaining)


def _read_plain(response: TransportResponse, max_bytes: int, deadline: float) -> bytes:
    body = bytearray()
    while True:
        _set_remaining_timeout(response, deadline)
        chunk = response.read(min(65_536, max_bytes + 1 - len(body)))
        if not chunk:
            return bytes(body)
        body.extend(chunk)
        if len(body) > max_bytes:
            _raise_too_large()


def _read_compressed(
    response: TransportResponse, max_bytes: int, encoding: str, deadline: float
) -> bytes:
    window_bits = zlib.MAX_WBITS | 16 if encoding in {"gzip", "x-gzip"} else zlib.MAX_WBITS
    decompressor = zlib.decompressobj(window_bits)
    body = bytearray()
    transferred = 0
    try:
        while True:
            _set_remaining_timeout(response, deadline)
            chunk = response.read(min(65_536, max_bytes + 1 - transferred))
            if not chunk:
                break
            transferred += len(chunk)
            if transferred > max_bytes:
                _raise_too_large()
            pending = chunk
            while pending:
                decoded = decompressor.decompress(pending, max_bytes + 1 - len(body))
                body.extend(decoded)
                if len(body) > max_bytes:
                    _raise_too_large()
                pending = decompressor.unconsumed_tail
        body.extend(decompressor.flush(max_bytes + 1 - len(body)))
    except zlib.error as error:
        raise SafeFetchError(SafeFetchErrorCode.INVALID_CONTENT_ENCODING) from error
    if len(body) > max_bytes:
        _raise_too_large()
    if not decompressor.eof:
        raise SafeFetchError(SafeFetchErrorCode.INVALID_CONTENT_ENCODING)
    return bytes(body)


def _read_success_response(
    response: TransportResponse,
    *,
    max_bytes: int,
    allowed_content_types: set[str],
    deadline: float,
) -> tuple[bytes, str]:
    if response.status in {408, 425, 429} or response.status >= 500:
        raise SafeFetchError(SafeFetchErrorCode.TEMPORARY_FAILURE, retryable=True)
    if response.status < 200 or response.status >= 300:
        raise SafeFetchError(SafeFetchErrorCode.HTTP_ERROR)

    content_type = _header_value(response.headers, "content-type")
    content_type = content_type.split(";", 1)[0].strip().lower()
    if content_type not in allowed_content_types:
        raise SafeFetchError(SafeFetchErrorCode.UNSUPPORTED_CONTENT_TYPE)

    content_length = _header_value(response.headers, "content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                _raise_too_large()
        except ValueError:
            pass

    encoding = _header_value(response.headers, "content-encoding").lower()
    if encoding in {"", "identity"}:
        body = _read_plain(response, max_bytes, deadline)
    elif encoding in {"gzip", "x-gzip", "deflate"}:
        body = _read_compressed(response, max_bytes, encoding, deadline)
    else:
        raise SafeFetchError(SafeFetchErrorCode.UNSUPPORTED_CONTENT_ENCODING)
    return body, content_type


class SafeFetchClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        max_redirects: int = 5,
        per_host_concurrency: int = 2,
        per_host_minimum_interval_seconds: float = 0.1,
        user_agent: str = "CiteGuildBot/1.0",
        resolver: Resolver = resolve_public_addresses,
        transport: Transport = _default_transport,
    ):
        self.timeout_seconds = timeout_seconds
        self.max_redirects = max_redirects
        self.user_agent = user_agent
        self.resolver = resolver
        self.transport = transport
        self.rate_limiter = DomainRateLimiter(
            concurrency=per_host_concurrency,
            minimum_interval_seconds=per_host_minimum_interval_seconds,
        )

    @classmethod
    def from_django_settings(cls) -> SafeFetchClient:
        from django.conf import settings

        return cls(
            timeout_seconds=settings.CRAWL_REQUEST_TIMEOUT_SECONDS,
            max_redirects=settings.CRAWL_MAX_REDIRECTS,
            per_host_concurrency=min(settings.CRAWL_CONCURRENCY, 2),
        )

    def fetch(
        self,
        url: str,
        *,
        max_bytes: int,
        allowed_content_types: Set[str],
    ) -> SafeFetchResult:
        if max_bytes < 1 or not allowed_content_types:
            raise ValueError("max_bytes and allowed_content_types must be non-empty")
        normalized_types = {value.lower().strip() for value in allowed_content_types}
        current_url = url
        visited: set[str] = set()

        for redirect_count in range(self.max_redirects + 1):
            target = _build_target(current_url, self.resolver)
            if target.normalized_url in visited:
                raise SafeFetchError(SafeFetchErrorCode.TOO_MANY_REDIRECTS)
            visited.add(target.normalized_url)
            headers = {
                "Host": _format_host(target.hostname, target.port, target.scheme),
                "User-Agent": self.user_agent,
                "Accept": ", ".join(sorted(normalized_types)),
                "Accept-Encoding": "gzip, deflate",
            }

            try:
                with self.rate_limiter.acquire(
                    target.hostname,
                    timeout_seconds=self.timeout_seconds,
                ):
                    deadline = time.monotonic() + self.timeout_seconds
                    response = self.transport(target, headers, self.timeout_seconds)
                    try:
                        if 300 <= response.status < 400:
                            location = _header_value(response.headers, "location")
                            if not location or redirect_count >= self.max_redirects:
                                raise SafeFetchError(SafeFetchErrorCode.TOO_MANY_REDIRECTS)
                            current_url = urljoin(target.normalized_url, location)
                            continue

                        body, content_type = _read_success_response(
                            response,
                            max_bytes=max_bytes,
                            allowed_content_types=normalized_types,
                            deadline=deadline,
                        )

                        return SafeFetchResult(
                            body=body,
                            content_type=content_type,
                            final_url=target.normalized_url,
                            status=response.status,
                            redirect_count=redirect_count,
                        )
                    finally:
                        response.close()
            except SafeFetchError:
                raise
            except TimeoutError as error:
                raise SafeFetchError(SafeFetchErrorCode.TIMEOUT, retryable=True) from error
            except ssl.SSLError as error:
                raise SafeFetchError(SafeFetchErrorCode.TLS_ERROR) from error
            except (OSError, http.client.HTTPException) as error:
                raise SafeFetchError(SafeFetchErrorCode.UNREACHABLE, retryable=True) from error

        raise SafeFetchError(SafeFetchErrorCode.TOO_MANY_REDIRECTS)
