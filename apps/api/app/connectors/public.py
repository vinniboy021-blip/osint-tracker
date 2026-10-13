"""RSS/Atom, bounded OpenStreetMap and free defensive IOC lookup."""

from __future__ import annotations

import ipaddress
import re
from typing import Any

from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]
from defusedxml.ElementTree import fromstring  # type: ignore[import-untyped]

from .base import LIMIT_SCHEMA, TOKEN_SCHEMA, Connector, NormalizedObservation, domain_query, maximum
from .security import ConnectorError, validate_public_url


def _text(element: Any, local_name: str) -> str:
    for child in element:
        if child.tag.rsplit("}", 1)[-1] == local_name:
            return "".join(child.itertext()).strip()[:20000]
    return ""


class RSSConnector(Connector):
    id = "rss"
    name = "RSS / Atom / notícias públicas"
    description = "Feed HTTPS público explicitamente autorizado, com parser XML sem entidades externas"
    capabilities = ["public_news", "public_posts", "rss", "atom"]
    limitations = [
        "Sem HTML scraping; feed HTTPS direto e sem redirecionamento",
        "Exige authorized=true para confirmar uso permitido",
        "URLs dinâmicas usam DNS validado no momento da conexão",
    ]
    config_schema = {
        "type": "object",
        "required": ["authorized"],
        "properties": {"authorized": {"type": "boolean", "const": True}, "limit": LIMIT_SCHEMA},
    }

    def validate_config(self, config: dict[str, Any]) -> None:
        super().validate_config(config)
        if config.get("authorized") is not True:
            raise ConnectorError(
                "Confirme que o feed público tem acesso permitido (authorized=true)", category="configuration"
            )

    def validate_query(self, query: str) -> str:
        validate_public_url(query)
        return query

    def collect(self, query: str, config: dict[str, Any]) -> list[NormalizedObservation]:
        self.validate_config(config)
        feed_url = self.validate_query(query)
        body = self.http.request(
            "GET",
            feed_url,
            headers={"Accept": "application/rss+xml, application/atom+xml, application/xml"},
            interval=2,
        )
        try:
            root = fromstring(body, forbid_dtd=True, forbid_entities=True, forbid_external=True)
        except (DefusedXmlException, ValueError, SyntaxError) as exc:
            raise ConnectorError("Feed XML inválido ou com entidades proibidas", category="format") from exc
        kind = root.tag.rsplit("}", 1)[-1]
        if kind not in ("rss", "feed", "RDF"):
            raise ConnectorError("A fonte não é um feed RSS/Atom suportado", category="format")
        entries = [entry for entry in root.iter() if entry.tag.rsplit("}", 1)[-1] in ("item", "entry")]
        results = []
        for entry in entries[: maximum(config)]:
            title = _text(entry, "title")
            url = _text(entry, "link")
            for child in entry:
                if (
                    child.tag.rsplit("}", 1)[-1] == "link"
                    and child.attrib.get("rel", "alternate") == "alternate"
                ):
                    url = child.attrib.get("href", "") or url
            if not url:
                url = feed_url
            try:
                validate_public_url(url)
            except ConnectorError:
                url = feed_url
            identifier = _text(entry, "id") or _text(entry, "guid") or url
            data = {
                "title": title,
                "url": url,
                "feed_url": feed_url,
                "published_at": _text(entry, "published") or _text(entry, "pubDate"),
                "updated_at": _text(entry, "updated"),
                "summary": _text(entry, "summary") or _text(entry, "description"),
                "content": _text(entry, "content") or _text(entry, "encoded"),
            }
            results.append(
                self.observation(
                    url,
                    identifier,
                    data,
                    entity_type="document",
                    entity_value=url,
                    label=title,
                    method="authorized_public_feed",
                )
            )
        return results


class OpenStreetMapConnector(Connector):
    id = "osm"
    name = "OpenStreetMap"
    description = "Objeto público explícito ou geocodificação limitada por bounding box"
    capabilities = ["public_geo_object", "bounded_geocoding"]
    limitations = [
        "Nominatim: máximo 1 requisição/segundo; consultas devem ser cacheadas",
        "Sem autocomplete, busca em massa ou monitoramento intensivo",
        "Busca exige bbox com área de até 1 grau por eixo; atribuição © OpenStreetMap contributors",
    ]
    config_schema = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["object", "search"]},
            "bbox": {
                "type": "array",
                "minItems": 4,
                "maxItems": 4,
                "items": {"type": "number"},
                "description": "[min_lon,min_lat,max_lon,max_lat]",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 5, "default": 5},
        },
    }

    def validate_config(self, config: dict[str, Any]) -> None:
        super().validate_config(config)
        maximum(config, cap=5, default=5)
        mode = config.get("mode", "object")
        if mode not in ("object", "search"):
            raise ConnectorError("Modo OSM inválido")
        if mode == "search":
            bbox = config.get("bbox")
            if (
                not isinstance(bbox, list)
                or len(bbox) != 4
                or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in bbox)
            ):
                raise ConnectorError("Busca OSM exige bbox [min_lon,min_lat,max_lon,max_lat]")
            min_lon, min_lat, max_lon, max_lat = bbox
            if not (
                -180 <= min_lon < max_lon <= 180
                and -90 <= min_lat < max_lat <= 90
                and max_lon - min_lon <= 1
                and max_lat - min_lat <= 1
            ):
                raise ConnectorError("Bounding box inválida ou maior que 1 grau por eixo")

    def validate_query(self, query: str) -> str:
        query = super().validate_query(query)
        if len(query) > 200 or "https://" in query or any(ord(char) < 32 for char in query):
            raise ConnectorError("Consulta OSM inválida")
        return query

    def collect(self, query: str, config: dict[str, Any]) -> list[NormalizedObservation]:
        self.validate_config(config)
        query = self.validate_query(query)
        if config.get("mode", "object") == "object":
            match = re.fullmatch(r"(node|way|relation)/([0-9]{1,15})", query)
            if not match:
                raise ConnectorError("Informe node/ID, way/ID ou relation/ID público explícito")
            kind, object_id = match.groups()
            payload = self.http.json(
                "GET", f"https://www.openstreetmap.org/api/0.6/{kind}/{object_id}.json", interval=1
            )
            rows = payload.get("elements", [])
        else:
            min_lon, min_lat, max_lon, max_lat = config["bbox"]
            params = {
                "q": query,
                "format": "jsonv2",
                "bounded": 1,
                "viewbox": f"{min_lon},{max_lat},{max_lon},{min_lat}",
                "limit": maximum(config, cap=5, default=5),
            }
            rows = self.http.json(
                "GET",
                "https://nominatim.openstreetmap.org/search",
                params=params,
                headers={"Accept-Language": "pt-BR"},
                interval=1,
            )
        results = []
        for row in rows[: maximum(config, cap=5, default=5)]:
            kind = row.get("osm_type") or row.get("type")
            object_id = row.get("osm_id") or row.get("id")
            if kind not in ("node", "way", "relation") or not object_id:
                continue
            url = f"https://www.openstreetmap.org/{kind}/{object_id}"
            data = {**row, "attribution": "© OpenStreetMap contributors", "license": "ODbL"}
            results.append(
                self.observation(
                    url,
                    f"{kind}/{object_id}",
                    data,
                    entity_type="event",
                    entity_value=url,
                    label=row.get("display_name") or row.get("tags", {}).get("name"),
                )
            )
        return results


class URLhausConnector(Connector):
    id = "urlhaus"
    name = "URLhaus / abuse.ch"
    description = "Consulta defensiva de domínio ou IP em indicadores públicos, com chave gratuita"
    requires_credentials = True
    token_env = "OSINT_URLHAUS_AUTH_KEY"
    capabilities = ["public_threat_indicator", "domain_ip_enrichment"]
    limitations = [
        "API abuse.ch exige Auth-Key gratuita configurada",
        "Somente lookup exato; nunca visita URLs maliciosas",
        "Um registro no feed não comprova atividade maliciosa atual do host",
    ]
    config_schema = {
        "type": "object",
        "properties": {
            "token": {**TOKEN_SCHEMA, "description": "Auth-Key gratuita do abuse.ch"},
            "limit": LIMIT_SCHEMA,
        },
    }

    def validate_query(self, query: str) -> str:
        try:
            address = ipaddress.ip_address(query)
        except ValueError:
            return domain_query(query)
        if not address.is_global:
            raise ConnectorError("Lookup público exige IP global ou domínio")
        return str(address)

    def collect(self, query: str, config: dict[str, Any]) -> list[NormalizedObservation]:
        self.validate_config(config)
        query = self.validate_query(query)
        config = self.effective_config(config)
        endpoint = "https://urlhaus-api.abuse.ch/v1/host/"
        payload = self.http.json(
            "POST", endpoint, headers={"Auth-Key": config["token"]}, form={"host": query}, interval=2
        )
        if payload.get("query_status") == "no_results":
            return []
        if payload.get("query_status") != "ok":
            raise ConnectorError("URLhaus recusou a consulta ou chave", category="source")
        results = []
        for row in payload.get("urls", [])[: maximum(config)]:
            identifier = str(row.get("id", ""))
            if not identifier:
                continue
            data = {
                "indicator": query,
                "classification": "feed_sighting",
                "confidence": 0.8,
                "explanation": "Registro observado no feed URLhaus; não implica comprometimento atual",
                **{
                    key: row[key]
                    for key in (
                        "id",
                        "url",
                        "url_status",
                        "date_added",
                        "last_online",
                        "threat",
                        "tags",
                        "urlhaus_reference",
                    )
                    if key in row
                },
            }
            source_url = row.get("urlhaus_reference", f"https://urlhaus.abuse.ch/url/{identifier}/")
            results.append(
                self.observation(
                    source_url, identifier, data, entity_type="threat_indicator", entity_value=query
                )
            )
        return results
