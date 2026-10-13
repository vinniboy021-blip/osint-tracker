"""Validated public identifiers for defensive intelligence; no active probing."""

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit


def normalize_identifier(entity_type: str, value: str) -> str:
    value = value.strip()
    if not value or len(value) > 2048 or any(ord(char) < 32 for char in value):
        raise ValueError("Identificador vazio, longo ou com caracteres de controle")
    if entity_type in {"domain", "subdomain"}:
        domain = value.rstrip(".").encode("idna").decode("ascii").lower()
        if len(domain) > 253 or not all(
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in domain.split(".")
        ):
            raise ValueError("Domínio inválido")
        return domain
    if entity_type == "ip":
        return str(ipaddress.ip_address(value))
    if entity_type == "sha256":
        if not re.fullmatch(r"[A-Fa-f0-9]{64}", value):
            raise ValueError("SHA-256 inválido")
        return value.lower()
    if entity_type in {"url", "website"}:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("URL HTTP(S) sem credenciais obrigatória")
        host = parts.hostname.encode("idna").decode("ascii").lower()
        if ":" in host:
            host = f"[{host}]"
        port = parts.port
        if port and not (parts.scheme == "https" and port == 443 or parts.scheme == "http" and port == 80):
            host += f":{port}"
        return urlunsplit((parts.scheme.lower(), host, parts.path or "/", parts.query, ""))
    if entity_type in {"username", "email"}:
        # Equality is an identifier match, never proof that people are identical.
        return value.lower()
    return value


def validate_indicator(indicator_type: str, value: str) -> str:
    if indicator_type not in {"ip", "domain", "sha256", "url"}:
        raise ValueError("Tipo de indicador não suportado")
    return normalize_identifier(indicator_type, value)


def safe_source_url(value: str | None) -> str | None:
    """Metadata only: this function does not acquire or resolve the provided URL."""
    if not value:
        return None
    return normalize_identifier("url", value)
