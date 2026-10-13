"""Stable contracts between connectors, normalization and collection workers."""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator

from .security import ConnectorError, http


class NormalizedObservation(BaseModel):
    source_name: str
    source_url: str
    acquisition_method: str = "official_public_api"
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    external_id: str
    data: dict[str, Any]
    entity_type: str | None = None
    entity_value: str | None = None
    entity_label: str | None = None

    @field_validator("collected_at")
    @classmethod
    def aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("collected_at exige timezone")
        return value.astimezone(UTC)


def domain_query(query: str) -> str:
    if not isinstance(query, str) or len(query) > 253 or any(char in query for char in "/:@* \\"):
        raise ConnectorError("Informe um domínio exato, sem URL, wildcard ou porta")
    try:
        domain = query.strip().rstrip(".").lower().encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ConnectorError("Domínio inválido") from exc
    labels = domain.split(".")
    if len(labels) < 2 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels
    ):
        raise ConnectorError("Domínio inválido")
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,62}", labels[-1]):
        raise ConnectorError("Domínio inválido")
    return domain


def identifier_query(query: str) -> str:
    if not isinstance(query, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", query):
        raise ConnectorError("Identificador público inválido")
    return query


def maximum(config: dict[str, Any], cap: int = 100, default: int = 30) -> int:
    value = config.get("limit", default)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= cap:
        raise ConnectorError(f"limit deve estar entre 1 e {cap}")
    return value


class Connector:
    id: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str]
    requires_credentials: ClassVar[bool] = False
    limitations: ClassVar[list[str]] = []
    capabilities: ClassVar[list[str]] = []
    config_schema: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}
    token_env: ClassVar[str | None] = None

    def __init__(self) -> None:
        self.http = http

    def effective_config(self, config: dict[str, Any]) -> dict[str, Any]:
        effective = dict(config)
        if self.token_env and not effective.get("token"):
            token = os.getenv(self.token_env)
            if token:
                effective["token"] = token
        return effective

    def validate_config(self, config: dict[str, Any]) -> None:
        if not isinstance(config, dict):
            raise ConnectorError("A configuração precisa ser um objeto")
        maximum(config)
        if self.requires_credentials and not self.effective_config(config).get("token"):
            raise ConnectorError("Credencial oficial não configurada", category="configuration")

    def validate_query(self, query: str) -> str:
        if not isinstance(query, str) or not query.strip() or len(query) > 512:
            raise ConnectorError("Consulta pública inválida")
        return query.strip()

    def descriptor(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "requires_credentials": self.requires_credentials,
            "limitations": self.limitations,
            "config_schema": self.config_schema,
            "capabilities": self.capabilities,
        }

    def health(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            self.validate_config(config or {})
        except ConnectorError as exc:
            return {"status": "needs_configuration", "category": exc.category, "message": str(exc)}
        return {
            "status": "configured",
            "message": "Pronto para coleta; disponibilidade verificada em cada execução",
        }

    def observation(
        self,
        url: str,
        external_id: str,
        data: dict[str, Any],
        *,
        entity_type: str | None = None,
        entity_value: str | None = None,
        label: str | None = None,
        method: str = "official_public_api",
    ) -> NormalizedObservation:
        return NormalizedObservation(
            source_name=self.id,
            source_url=url,
            external_id=external_id,
            data=data,
            entity_type=entity_type,
            entity_value=entity_value,
            entity_label=label,
            acquisition_method=method,
        )

    def collect(self, query: str, config: dict[str, Any]) -> list[NormalizedObservation]:
        raise NotImplementedError


LIMIT_SCHEMA = {"type": "integer", "minimum": 1, "maximum": 100, "default": 30}
TOKEN_SCHEMA = {"type": "string", "writeOnly": True, "description": "Credencial opcional protegida"}
