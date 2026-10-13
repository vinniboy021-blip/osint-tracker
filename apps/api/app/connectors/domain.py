"""Passive domain sources; no ports, zone transfers or target probing."""

from __future__ import annotations

from typing import Any

from .base import LIMIT_SCHEMA, Connector, NormalizedObservation, domain_query, maximum
from .security import ConnectorError, validate_public_url


class RDAPConnector(Connector):
    id = "rdap"
    name = "RDAP"
    description = "Registro público de um domínio exato, resolvido pelo bootstrap oficial IANA"
    capabilities = ["domain_registration", "domain_metadata"]
    limitations = ["Dados pessoais de contatos são minimizados", "Disponibilidade depende do registro do TLD"]

    def validate_query(self, query: str) -> str:
        return domain_query(query)

    def collect(self, query: str, config: dict[str, Any]) -> list[NormalizedObservation]:
        self.validate_config(config)
        domain = self.validate_query(query)
        suffix = domain.rsplit(".", 1)[1]
        if suffix in {"com", "net"}:
            base = f"https://rdap.verisign.com/{suffix}/v1/"
        else:
            bootstrap = self.http.json("GET", "https://data.iana.org/rdap/dns.json", interval=1)
            base = next(
                (urls[0] for tlds, urls in bootstrap.get("services", []) if suffix in tlds and urls), None
            )  # type: ignore[assignment]
            if not base:
                raise ConnectorError("TLD sem serviço RDAP no bootstrap oficial", category="source")
            validate_public_url(base)
        endpoint = f"{base.rstrip('/')}/domain/{domain}"
        record = self.http.json("GET", endpoint, headers={"Accept": "application/rdap+json"}, interval=1)
        if not isinstance(record, dict):
            raise ConnectorError("Resposta RDAP inválida", category="format")
        selected = {
            key: record[key]
            for key in ("ldhName", "unicodeName", "status", "events", "handle", "notices")
            if key in record
        }
        selected["nameservers"] = [
            item.get("ldhName") for item in record.get("nameservers", []) if item.get("ldhName")
        ]
        return [self.observation(endpoint, domain, selected, entity_type="domain", entity_value=domain)]


class DNSConnector(Connector):
    id = "dns"
    name = "DNS público"
    description = "Consulta passiva DNS over HTTPS; nenhuma conexão com os IPs retornados"
    capabilities = ["dns_records"]
    limitations = ["Somente A, AAAA, MX, NS, TXT, CNAME, SOA e CAA", "Não realiza AXFR nem enumeração"]
    config_schema = {
        "type": "object",
        "properties": {
            "record_type": {
                "type": "string",
                "enum": ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA", "CAA"],
            },
            "limit": LIMIT_SCHEMA,
        },
    }

    def validate_query(self, query: str) -> str:
        return domain_query(query)

    def validate_config(self, config: dict[str, Any]) -> None:
        super().validate_config(config)
        if config.get("record_type", "A") not in ("A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA", "CAA"):
            raise ConnectorError("Tipo de registro DNS não suportado")

    def collect(self, query: str, config: dict[str, Any]) -> list[NormalizedObservation]:
        self.validate_config(config)
        domain = self.validate_query(query)
        record_type = config.get("record_type", "A")
        url = "https://dns.google/resolve"
        payload = self.http.json("GET", url, params={"name": domain, "type": record_type}, interval=0.25)
        if payload.get("Status", 0) not in (0, 3):
            raise ConnectorError("Resolvedor DNS retornou uma falha", category="upstream", retryable=True)
        return [
            self.observation(
                f"{url}?name={domain}&type={record_type}",
                f"{domain}:{item.get('type')}:{item.get('data')}",
                {**item, "query": domain, "record_type": record_type},
                entity_type="domain",
                entity_value=domain,
            )
            for item in payload.get("Answer", [])[: maximum(config)]
        ]


class CertificateTransparencyConnector(Connector):
    id = "crtsh"
    name = "Certificate Transparency / crt.sh"
    description = "Certificados públicos associados a um domínio exato"
    capabilities = ["certificates", "public_domain_names"]
    limitations = [
        "Consulta exata, sem wildcard",
        "Fonte pode indisponibilizar consultas; limite 100 registros",
        "Certificado não comprova controle atual do domínio",
    ]
    config_schema = {"type": "object", "properties": {"limit": LIMIT_SCHEMA}}

    def validate_query(self, query: str) -> str:
        return domain_query(query)

    def collect(self, query: str, config: dict[str, Any]) -> list[NormalizedObservation]:
        self.validate_config(config)
        domain = self.validate_query(query)
        endpoint = "https://crt.sh/"
        payload = self.http.json("GET", endpoint, params={"q": domain, "output": "json"}, interval=5)
        if not isinstance(payload, list):
            raise ConnectorError("Resposta CT inválida", category="format")
        results: list[NormalizedObservation] = []
        seen: set[str] = set()
        for row in payload:
            certificate_id = str(row.get("id", ""))
            if not certificate_id or certificate_id in seen:
                continue
            seen.add(certificate_id)
            results.append(
                self.observation(
                    f"https://crt.sh/?id={certificate_id}",
                    certificate_id,
                    row,
                    entity_type="domain",
                    entity_value=domain,
                )
            )
            if len(results) >= maximum(config):
                break
        return results
