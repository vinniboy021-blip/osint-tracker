"""Bounded HTTPS transport with DNS validation at TCP connection time."""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import threading
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import httpcore
import httpx

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
# Only these application-owned official endpoints may use a trusted deployment proxy.
OFFICIAL_HOSTS = frozenset(
    {
        "rdap.org",
        "rdap.verisign.com",
        "data.iana.org",
        "dns.google",
        "crt.sh",
        "api.github.com",
        "gitlab.com",
        "public.api.bsky.app",
        "nominatim.openstreetmap.org",
        "www.openstreetmap.org",
        "urlhaus-api.abuse.ch",
        "graph.facebook.com",
    }
)


class ConnectorError(Exception):
    """Safe, serializable error; never contains credentials or upstream response bodies."""

    def __init__(self, message: str, *, category: str = "validation", retryable: bool = False):
        super().__init__(message)
        self.category = category
        self.retryable = retryable


def validate_public_url(url: str) -> tuple[str, int]:
    """Reject ambiguous URLs, credentials, internal destinations and unsafe protocols."""
    if not isinstance(url, str) or not url or len(url) > 2048 or any(ord(c) < 33 for c in url):
        raise ConnectorError("URL pública inválida", category="ssrf")
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port or 443
    except ValueError as exc:
        raise ConnectorError("URL pública inválida", category="ssrf") from exc
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port != 443
        or "\\" in url
        or parsed.fragment
    ):
        raise ConnectorError("Somente HTTPS público na porta 443, sem credenciais na URL", category="ssrf")
    hostname = hostname.rstrip(".").lower()
    if (
        hostname == "localhost"
        or "." not in hostname
        or hostname.endswith((".localhost", ".local", ".internal"))
    ):
        raise ConnectorError("Destino interno bloqueado", category="ssrf")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ConnectorError("Hostname inválido", category="ssrf") from exc
    else:
        if not _public_address(address):
            raise ConnectorError("Endereço não público bloqueado", category="ssrf")
    return hostname, port


def _public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return _public_address(address.ipv4_mapped)
    # Teredo / 6to4 embed an IPv4 destination: disallow these transition mechanisms.
    if isinstance(address, ipaddress.IPv6Address) and (address.sixtofour or address.teredo):
        return False
    return address.is_global and not address.is_multicast and not address.is_reserved


def resolve_public_addresses(host: str, port: int = 443) -> list[str]:
    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ConnectorError("Falha na resolução DNS da fonte", category="network", retryable=True) from exc
    addresses: list[str] = []
    for answer in answers:
        address = str(answer[4][0])
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ConnectorError("Resposta DNS inválida", category="ssrf") from exc
        if not _public_address(parsed):
            raise ConnectorError("DNS resolveu para destino não público", category="ssrf")
        if address not in addresses:
            addresses.append(address)
    if not addresses:
        raise ConnectorError("Fonte sem endereço público", category="network", retryable=True)
    return addresses


class PublicNetworkBackend(httpcore.SyncBackend):
    """Connect to a vetted numeric address; httpcore keeps the hostname for TLS/SNI."""

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> Any:
        if port != 443:
            raise ConnectorError("Porta externa não autorizada", category="ssrf")
        addresses = resolve_public_addresses(host, port)
        last_error: Exception | None = None
        for address in addresses:
            try:
                return super().connect_tcp(address, port, timeout, local_address, socket_options)
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        raise httpcore.ConnectError("Fonte pública inacessível") from last_error


class RateLimiter:
    """Atomic per-host permit via Redis when provided, otherwise process-local backpressure."""

    def __init__(self) -> None:
        self.redis: Any = None
        self._lock = threading.Lock()
        self._next: dict[str, float] = {}

    def acquire(self, host: str, interval: float) -> None:
        if self.redis is not None:
            try:
                allowed = self.redis.set(
                    f"osint:connector:rate:{host}", "1", nx=True, px=max(1, int(interval * 1000))
                )
            except Exception as exc:
                raise ConnectorError(
                    "Controle de limites indisponível", category="rate_limit", retryable=True
                ) from exc
            if not allowed:
                raise ConnectorError(
                    "Limite da fonte: aguarde a próxima execução", category="rate_limit", retryable=True
                )
            return
        with self._lock:
            now = time.monotonic()
            if self._next.get(host, 0) > now:
                raise ConnectorError(
                    "Limite da fonte: aguarde a próxima execução", category="rate_limit", retryable=True
                )
            self._next[host] = now + interval


limiter = RateLimiter()


class SafeHTTP:
    """No redirects; bounded retries and body. External response content stays out of errors."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout: float = 20,
        retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._test_client = client
        self.timeout = timeout
        self.retries = retries
        self.sleep = sleep

    def _client(self, host: str) -> httpx.Client:
        if self._test_client is not None:
            return self._test_client
        # The deployment proxy is trusted infrastructure, and only exact application-owned
        # endpoints can use it. Dynamic/user-supplied destinations always use DNS-pinned TCP.
        proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
        if host in OFFICIAL_HOSTS and proxy:
            return httpx.Client(
                proxy=proxy,
                timeout=self.timeout,
                follow_redirects=False,
                trust_env=True,
                headers={"User-Agent": "OSINT-Tracker/0.1 (passive public data)"},
            )
        transport = httpx.HTTPTransport(retries=0, trust_env=False)
        # httpx 0.28/httpcore 1.x do not expose network_backend on HTTPTransport.
        # Replacing this backend retains httpx exception mapping and TLS verification.
        transport._pool._network_backend = PublicNetworkBackend()
        return httpx.Client(
            transport=transport,
            timeout=self.timeout,
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": "OSINT-Tracker/0.1 (passive public data)"},
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        form: dict[str, str] | None = None,
        interval: float = 1.0,
    ) -> bytes:
        host, _ = validate_public_url(url)
        limiter.acquire(host, interval)
        client = self._client(host)
        try:
            for attempt in range(self.retries + 1):
                try:
                    with client.stream(method, url, params=params, headers=headers, data=form) as response:
                        if response.status_code in (401, 403):
                            raise ConnectorError(
                                "A fonte recusou as credenciais ou permissões", category="authorization"
                            )
                        if response.status_code == 429:
                            # Never immediately retry a server-imposed rate limit.
                            raise ConnectorError(
                                "Fonte limitou a taxa de requisições", category="rate_limit", retryable=True
                            )
                        if 300 <= response.status_code < 400:
                            raise ConnectorError(
                                "Redirecionamento da fonte exige endpoint HTTPS explícito", category="source"
                            )
                        if response.status_code == 404:
                            raise ConnectorError("Registro não encontrado na fonte", category="not_found")
                        if response.status_code >= 500:
                            raise ConnectorError(
                                "Fonte temporariamente indisponível", category="upstream", retryable=True
                            )
                        if not 200 <= response.status_code < 300:
                            raise ConnectorError("Fonte recusou a consulta", category="source")
                        length = response.headers.get("content-length")
                        if length and (not length.isdigit() or int(length) > MAX_RESPONSE_BYTES):
                            raise ConnectorError(
                                "Resposta da fonte excede o limite de tamanho", category="size"
                            )
                        result = bytearray()
                        for chunk in response.iter_bytes():
                            result.extend(chunk)
                            if len(result) > MAX_RESPONSE_BYTES:
                                raise ConnectorError(
                                    "Resposta da fonte excede o limite de tamanho", category="size"
                                )
                        return bytes(result)
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    error = ConnectorError("Falha de rede na fonte", category="network", retryable=True)
                    if attempt == self.retries:
                        raise error from exc
                except ConnectorError as exc:
                    if not exc.retryable or exc.category == "rate_limit" or attempt == self.retries:
                        raise
                self.sleep(min(2**attempt, 4))
        finally:
            if self._test_client is None:
                client.close()
        raise ConnectorError("Falha na coleta", category="network", retryable=True)

    def json(self, method: str, url: str, **kwargs: Any) -> Any:
        body = self.request(method, url, **kwargs)
        try:
            return json.loads(body)
        except (ValueError, UnicodeError) as exc:
            raise ConnectorError("A fonte retornou JSON inválido", category="format") from exc


http = SafeHTTP()
