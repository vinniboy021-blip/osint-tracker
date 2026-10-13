"""Reproducible exports from persisted records, with provenance and safe CSV cells."""

import csv
import io
import json
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import inspect


def json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (UUID, Enum)):
        return str(value)
    raise TypeError(f"Tipo não serializável: {type(value).__name__}")


def record_dict(record: Any) -> dict[str, Any]:
    # No ORM relationships or credentials are traversed.
    return {column.key: getattr(record, column.key) for column in inspect(record).mapper.column_attrs}


def safe_csv_cell(value: Any) -> str:
    cell = str(value if value is not None else "")
    if cell.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + cell
    return cell


def csv_export(records: list[dict[str, Any]]) -> str:
    out = io.StringIO(newline="")
    headers = sorted({key for record in records for key in record})
    writer = csv.DictWriter(out, fieldnames=headers)
    writer.writeheader()
    for record in records:
        writer.writerow(
            {
                key: safe_csv_cell(
                    json.dumps(value, ensure_ascii=False, default=json_default)
                    if isinstance(value, (dict, list))
                    else value
                )
                for key, value in record.items()
            }
        )
    return out.getvalue()


def generate_report(context: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json.dumps(context, ensure_ascii=False, indent=2, default=json_default)
    if output_format == "csv":
        records: list[dict[str, Any]] = []
        for category in ("observations", "entities", "evidence", "relationships", "threat_indicators"):
            records.extend({"record_type": category, **record} for record in context.get(category, []))
        return csv_export(records)
    if output_format != "md":
        raise ValueError("Formato não suportado")
    # JSON code blocks retain source text without rendering raw HTML from sources.
    title = str(context.get("title", "Relatório")).replace("\n", " ").replace("\r", " ")
    lines = [f"# {title}", "", "Dados persistidos; hipóteses não comprovam identidade.", ""]
    for category in (
        "investigation",
        "observations",
        "entities",
        "relationships",
        "evidence",
        "threat_indicators",
    ):
        lines.extend(
            [
                f"## {category}",
                "",
                "```json",
                json.dumps(
                    context.get(category, []), ensure_ascii=False, indent=2, default=json_default
                ).replace("```", "\\u0060\\u0060\\u0060"),
                "```",
                "",
            ]
        )
    return "\n".join(lines)
