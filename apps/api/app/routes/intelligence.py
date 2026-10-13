"""Investigation-scoped correlation, evidence, reporting and defensive intelligence."""

import json
from datetime import timedelta
from itertools import combinations
from typing import Annotated, Any, Literal
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import TASKS, cited_summary, local_model_hypotheses
from app.auth import current_user, investigation_access
from app.config import settings
from app.correlation import bounded_path, compare_entities
from app.db import get_db
from app.evidence import LocalStorage, capture_upload, download_chunks, safe_filename, verify_digest
from app.intelligence import safe_source_url, validate_indicator
from app.models import (
    AIAnalysisRun,
    Alert,
    AuditLog,
    CorrelationCandidate,
    CorrelationReview,
    Entity,
    EntityRelationship,
    Evidence,
    EvidenceVersion,
    Investigation,
    Observation,
    Report,
    ThreatIndicator,
    Timeline,
    User,
    utcnow,
)
from app.reporting import csv_export, generate_report, record_dict

router = APIRouter(tags=["intelligence"])
DB = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(current_user)]
Identifier = Annotated[str, Field(min_length=1, max_length=36)]


def public_record(record: Any) -> dict[str, Any]:
    result = record_dict(record)
    # Internal storage paths are not disclosed through HTTP.
    result.pop("storage_key", None)
    return result


def page(db: Session, model: Any, investigation_id: str, limit: int, offset: int) -> dict[str, Any]:
    where = model.investigation_id == investigation_id
    items: list[Any] = list(
        db.scalars(select(model).where(where).order_by(model.created_at.desc()).limit(limit).offset(offset))
    )
    return {
        "items": [public_record(item) for item in items],
        "total": db.scalar(select(func.count()).select_from(model).where(where)),
    }


def scoped_record(db: Session, user: User, model: Any, record_id: str, write: bool = False) -> Any:
    record = db.get(model, record_id)
    if record is None:
        raise HTTPException(404, "Registro não encontrado")
    investigation_access(db, user, record.investigation_id, write=write)
    return record


def audit(
    db: Session, user: User, investigation_id: str, action: str, record: Any, details: dict | None = None
):
    db.add(
        AuditLog(
            user_id=user.id,
            investigation_id=investigation_id,
            action=action,
            object_type=record.__tablename__,
            object_id=record.id,
            details=details or {},
        )
    )
    db.add(
        Timeline(
            investigation_id=investigation_id,
            event_type=action,
            title=action,
            details={"object_id": record.id, **(details or {})},
        )
    )


def context_for(db: Session, investigation_id: str, title: str = "Relatório") -> dict[str, Any]:
    investigation = db.get(Investigation, investigation_id)
    context: dict[str, Any] = {
        "title": title,
        "generated_at": utcnow(),
        "investigation": public_record(investigation),
    }
    # Explicit export limit avoids unbounded in-memory reports; totals make truncation visible.
    context["limits"] = {"per_category": 2000}
    for name, model in [
        ("observations", Observation),
        ("entities", Entity),
        ("evidence", Evidence),
        ("relationships", EntityRelationship),
        ("threat_indicators", ThreatIndicator),
    ]:
        query = select(model).where(model.investigation_id == investigation_id).order_by(model.created_at)  # type: ignore[attr-defined]
        context[name] = [public_record(item) for item in db.scalars(query.limit(2000))]
        context["limits"][f"{name}_total"] = db.scalar(  # type: ignore[index,arg-type]
            select(func.count()).select_from(model).where(model.investigation_id == investigation_id)  # type: ignore[attr-defined,arg-type]
        )
    return context


class InvestigationBody(BaseModel):
    investigation_id: Identifier


class ReviewBody(BaseModel):
    decision: Literal["confirmed", "rejected", "unverified"]
    notes: str = Field(default="", max_length=10000)
    evidence_ids: list[Identifier] = Field(default_factory=list, max_length=50)


@router.get("/correlations")
def correlations(
    db: DB,
    user: Actor,
    investigation_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    investigation_access(db, user, investigation_id)
    return page(db, CorrelationCandidate, investigation_id, limit, offset)


@router.post("/correlations/suggest")
def suggest(body: InvestigationBody, db: DB, user: Actor):
    investigation_access(db, user, body.investigation_id, write=True)
    # Locks the workspace so concurrent suggestions cannot violate pair uniqueness.
    db.execute(select(Investigation).where(Investigation.id == body.investigation_id).with_for_update())
    entities = list(
        db.scalars(
            select(Entity)
            .where(Entity.investigation_id == body.investigation_id)
            .order_by(Entity.id)
            .limit(301)
        )
    )
    if len(entities) > 300:
        raise HTTPException(422, "Mais de 300 entidades: reduza o escopo para sugerir correlações")
    existing = set(
        db.execute(
            select(
                CorrelationCandidate.source_entity_id,
                CorrelationCandidate.target_entity_id,
                CorrelationCandidate.rule,
            ).where(CorrelationCandidate.investigation_id == body.investigation_id)
        ).all()
    )
    created = []
    for a, b in combinations(entities, 2):
        match = compare_entities(a, b)
        if match is None or (a.id, b.id, match.rule) in existing:
            continue
        candidate = CorrelationCandidate(
            investigation_id=body.investigation_id,
            source_entity_id=a.id,
            target_entity_id=b.id,
            score=match.score,
            rule=match.rule,
            explanation=match.explanation,
            payload={"left": a.canonical_value, "right": b.canonical_value, "automatic_merge": False},
        )
        db.add(candidate)
        db.flush()
        audit(db, user, body.investigation_id, "correlation.suggested", candidate)
        created.append(candidate)
    db.commit()
    return {"items": [public_record(item) for item in created], "total": len(created)}


@router.post("/correlations/{candidate_id}/review")
def review(candidate_id: str, body: ReviewBody, db: DB, user: Actor):
    candidate = scoped_record(db, user, CorrelationCandidate, candidate_id, write=True)
    db.refresh(candidate, with_for_update=True)
    for entity_id in (candidate.source_entity_id, candidate.target_entity_id):
        entity = db.get(Entity, entity_id)
        if not entity or entity.investigation_id != candidate.investigation_id:
            raise HTTPException(422, "Entidades de investigação incompatível")
    for evidence_id in body.evidence_ids:
        evidence = db.get(Evidence, evidence_id)
        if not evidence or evidence.investigation_id != candidate.investigation_id:
            raise HTTPException(422, "Evidência fora do escopo")
    if body.decision == "confirmed" and not body.notes.strip():
        raise HTTPException(422, "Confirmação exige justificativa da revisão humana")
    previous = candidate.status
    candidate.status = body.decision
    relation = db.scalar(
        select(EntityRelationship).where(
            EntityRelationship.investigation_id == candidate.investigation_id,
            EntityRelationship.source_entity_id == candidate.source_entity_id,
            EntityRelationship.target_entity_id == candidate.target_entity_id,
            EntityRelationship.relationship_type == "identifier_association",
        )
    )
    if relation is None:
        relation = EntityRelationship(
            investigation_id=candidate.investigation_id,
            source_entity_id=candidate.source_entity_id,
            target_entity_id=candidate.target_entity_id,
            relationship_type="identifier_association",
        )
        db.add(relation)
    relation.status = body.decision
    relation.confidence = candidate.score
    relation.explanation = candidate.explanation + " Revisão: " + body.notes
    relation.evidence_ids = list(dict.fromkeys(body.evidence_ids))
    db.add(
        CorrelationReview(
            candidate_id=candidate.id, reviewer_id=user.id, decision=body.decision, notes=body.notes
        )
    )
    db.flush()
    audit(
        db,
        user,
        candidate.investigation_id,
        "correlation.reviewed",
        candidate,
        {
            "previous_status": previous,
            "decision": body.decision,
            "notes": body.notes,
            "evidence_ids": body.evidence_ids,
        },
    )
    if body.decision == "confirmed" and previous != "confirmed":
        db.add(
            Alert(
                investigation_id=candidate.investigation_id,
                event_type="relationship_confirmed",
                title="Associação revisada e confirmada",
                details={"relationship_id": relation.id},
                dedupe_key=f"correlation:{candidate.id}:confirmed:{utcnow().isoformat()}",
            )
        )
    db.commit()
    return {"candidate": public_record(candidate), "relationship": public_record(relation)}


@router.get("/graph")
def graph(
    db: DB,
    user: Actor,
    investigation_id: str,
    node_limit: int = Query(200, ge=1, le=500),
    edge_limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    status: Literal["confirmed", "probable", "unverified"] | None = None,
    entity_type: str | None = Query(None, max_length=60),
):
    investigation_access(db, user, investigation_id)
    query = select(Entity).where(Entity.investigation_id == investigation_id)
    if entity_type:
        query = query.where(Entity.type == entity_type)
    entities = list(db.scalars(query.order_by(Entity.id).offset(offset).limit(node_limit + 1)))
    more_nodes = len(entities) > node_limit
    entities = entities[:node_limit]
    ids = [entity.id for entity in entities]
    edge_query = select(EntityRelationship).where(
        EntityRelationship.investigation_id == investigation_id,
        EntityRelationship.source_entity_id.in_(ids),
        EntityRelationship.target_entity_id.in_(ids),
        EntityRelationship.status != "rejected",
    )
    if status:
        edge_query = edge_query.where(EntityRelationship.status == status)
    edges = list(db.scalars(edge_query.order_by(EntityRelationship.id).limit(edge_limit + 1)))
    return {
        "nodes": [
            {"data": {"id": entity.id, "label": entity.label, "type": entity.type}} for entity in entities
        ],
        "edges": [
            {
                "data": {
                    "id": edge.id,
                    "source": edge.source_entity_id,
                    "target": edge.target_entity_id,
                    "label": edge.relationship_type,
                    "status": edge.status,
                    "confidence": edge.confidence,
                    "explanation": edge.explanation,
                    "evidence_ids": edge.evidence_ids,
                }
            }
            for edge in edges[:edge_limit]
        ],
        "truncated": more_nodes or len(edges) > edge_limit,
        "next_offset": offset + node_limit if more_nodes else None,
    }


@router.get("/graph/path")
def path(
    db: DB,
    user: Actor,
    investigation_id: str,
    source: str,
    target: str,
    max_depth: int = Query(6, ge=1, le=10),
):
    investigation_access(db, user, investigation_id)
    for entity_id in (source, target):
        entity = db.get(Entity, entity_id)
        if not entity or entity.investigation_id != investigation_id:
            raise HTTPException(404, "Entidade não encontrada no escopo")
    edges = list(
        db.scalars(
            select(EntityRelationship)
            .where(
                EntityRelationship.investigation_id == investigation_id,
                EntityRelationship.status == "confirmed",
            )
            .order_by(EntityRelationship.id)
            .limit(5001)
        )
    )
    if len(edges) > 5000:
        raise HTTPException(422, "Grafo excede o limite para busca de caminhos; reduza o escopo")
    return {
        "path": bounded_path(source, target, edges, max_depth),
        "confirmed_only": True,
        "max_depth": max_depth,
    }


@router.get("/evidence")
def evidence_list(
    db: DB,
    user: Actor,
    investigation_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    investigation_access(db, user, investigation_id)
    return page(db, Evidence, investigation_id, limit, offset)


@router.post("/evidence", status_code=201)
async def upload_evidence(
    db: DB,
    user: Actor,
    investigation_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    source_url: Annotated[str, Form()] = "",
    notes: Annotated[str, Form(max_length=10000)] = "",
    entity_id: Annotated[str | None, Form()] = None,
    retention_days: Annotated[int | None, Form(ge=1, le=3650)] = None,
):
    investigation_access(db, user, investigation_id, write=True)
    if entity_id:
        entity = db.get(Entity, entity_id)
        if not entity or entity.investigation_id != investigation_id:
            raise HTTPException(422, "Entidade fora do escopo")
    storage = LocalStorage(settings.evidence_path)
    try:
        source = safe_source_url(source_url) or ""
        key, sha, size = await capture_upload(file, storage, settings.evidence_max_bytes)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    evidence = Evidence(
        investigation_id=investigation_id,
        entity_id=entity_id,
        filename=safe_filename(file.filename),
        content_type=(file.content_type or "application/octet-stream")[:150],
        storage_key=key,
        sha256=sha,
        size_bytes=size,
        source_url=source,
        collected_at=utcnow(),
        notes=notes,
        retention_until=utcnow() + timedelta(days=retention_days) if retention_days else None,
    )
    try:
        db.add(evidence)
        db.flush()
        db.add(
            EvidenceVersion(evidence_id=evidence.id, version=1, sha256=sha, storage_key=key, size_bytes=size)
        )
        audit(db, user, investigation_id, "evidence.added", evidence, {"sha256": sha, "size_bytes": size})
        db.add(
            Alert(
                investigation_id=investigation_id,
                event_type="evidence_added",
                title="Evidência adicionada",
                details={"evidence_id": evidence.id},
                dedupe_key=f"evidence:{evidence.id}:added",
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    return public_record(evidence)


@router.get("/evidence/{evidence_id}/download")
def evidence_download(evidence_id: str, db: DB, user: Actor, version: int | None = Query(None, ge=1)):
    evidence = scoped_record(db, user, Evidence, evidence_id)
    key = evidence.storage_key
    if version:
        item = db.scalar(
            select(EvidenceVersion).where(
                EvidenceVersion.evidence_id == evidence_id, EvidenceVersion.version == version
            )
        )
        if not item:
            raise HTTPException(404, "Versão não encontrada")
        key = item.storage_key
    storage = LocalStorage(settings.evidence_path)
    try:
        with storage.open(key):
            pass
    except FileNotFoundError as exc:
        raise HTTPException(410, "Arquivo indisponível ou expurgado") from exc
    audit(db, user, evidence.investigation_id, "evidence.downloaded", evidence, {"version": version})
    db.commit()
    return StreamingResponse(
        download_chunks(storage, key),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(evidence.filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
            "Content-Security-Policy": "sandbox",
        },
    )


@router.post("/evidence/{evidence_id}/verify")
def evidence_verify(evidence_id: str, db: DB, user: Actor):
    evidence = scoped_record(db, user, Evidence, evidence_id)
    try:
        valid = verify_digest(LocalStorage(settings.evidence_path), evidence.storage_key, evidence.sha256)
    except FileNotFoundError:
        valid = False
    audit(
        db,
        user,
        evidence.investigation_id,
        "evidence.verified",
        evidence,
        {"valid": valid, "sha256": evidence.sha256},
    )
    db.commit()
    return {"id": evidence.id, "valid": valid, "sha256": evidence.sha256}


@router.get("/evidence/{evidence_id}/versions")
def evidence_versions(evidence_id: str, db: DB, user: Actor):
    scoped_record(db, user, Evidence, evidence_id)
    items = db.scalars(
        select(EvidenceVersion)
        .where(EvidenceVersion.evidence_id == evidence_id)
        .order_by(EvidenceVersion.version)
    )
    records = [public_record(item) for item in items]
    return {"items": records, "total": len(records)}


@router.post("/evidence/{evidence_id}/versions", status_code=201)
async def evidence_version_upload(evidence_id: str, db: DB, user: Actor, file: Annotated[UploadFile, File()]):
    evidence = scoped_record(db, user, Evidence, evidence_id, write=True)
    db.refresh(evidence, with_for_update=True)
    storage = LocalStorage(settings.evidence_path)
    try:
        key, sha, size = await capture_upload(file, storage, settings.evidence_max_bytes)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    version = (
        db.scalar(select(func.max(EvidenceVersion.version)).where(EvidenceVersion.evidence_id == evidence_id))
        or 0
    ) + 1
    item = EvidenceVersion(
        evidence_id=evidence_id, version=version, sha256=sha, storage_key=key, size_bytes=size
    )
    try:
        db.add(item)
        evidence.storage_key, evidence.sha256, evidence.size_bytes = key, sha, size
        audit(
            db,
            user,
            evidence.investigation_id,
            "evidence.versioned",
            evidence,
            {"version": version, "sha256": sha},
        )
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    return public_record(item)


@router.delete("/evidence/{evidence_id}")
def evidence_delete(evidence_id: str, db: DB, user: Actor):
    evidence = scoped_record(db, user, Evidence, evidence_id, write=True)
    db.refresh(evidence, with_for_update=True)
    versions = list(db.scalars(select(EvidenceVersion).where(EvidenceVersion.evidence_id == evidence_id)))
    keys = {evidence.storage_key, *(version.storage_key for version in versions)}
    audit(
        db,
        user,
        evidence.investigation_id,
        "evidence.purged",
        evidence,
        {
            "sha256": evidence.sha256,
            "versions": [{"version": version.version, "sha256": version.sha256} for version in versions],
        },
    )
    # Remove all references so a graph cannot suggest purged evidence is available.
    for relation in db.scalars(
        select(EntityRelationship).where(EntityRelationship.investigation_id == evidence.investigation_id)
    ):
        if evidence_id in relation.evidence_ids:
            relation.evidence_ids = [ref for ref in relation.evidence_ids if ref != evidence_id]
    for version in versions:
        db.delete(version)
    db.delete(evidence)
    db.commit()
    storage = LocalStorage(settings.evidence_path)
    for key in keys:
        storage.delete(key)
    return {"deleted": True, "versions_removed": len(versions), "audit_preserved": True}


class ReportBody(InvestigationBody):
    title: str = Field(default="Relatório de investigação", min_length=1, max_length=250)
    format: Literal["json", "csv", "md"] = "json"


@router.get("/reports")
def reports(
    db: DB,
    user: Actor,
    investigation_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    investigation_access(db, user, investigation_id)
    result = page(db, Report, investigation_id, limit, offset)
    for item in result["items"]:
        item.pop("content", None)
    return result


@router.post("/reports", status_code=201)
def create_report(body: ReportBody, db: DB, user: Actor):
    investigation_access(db, user, body.investigation_id, write=True)
    report = Report(
        investigation_id=body.investigation_id,
        title=body.title,
        format=body.format,
        content=generate_report(context_for(db, body.investigation_id, body.title), body.format),
    )
    db.add(report)
    db.flush()
    audit(db, user, body.investigation_id, "report.generated", report, {"format": body.format})
    db.commit()
    result = public_record(report)
    result.pop("content", None)
    return result


@router.get("/reports/{report_id}/download")
def report_download(report_id: str, db: DB, user: Actor):
    report = scoped_record(db, user, Report, report_id)
    media_type = {"json": "application/json", "csv": "text/csv", "md": "text/markdown"}[report.format]
    return Response(
        report.content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="report-{report.id}.{report.format}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


class AIBody(InvestigationBody):
    task: str = Field(default="summary", max_length=30)


@router.post("/ai/analyze", status_code=201)
async def ai_analyze(body: AIBody, db: DB, user: Actor):
    investigation_access(db, user, body.investigation_id, write=True)
    if body.task not in TASKS:
        raise HTTPException(422, "Tarefa de IA inválida")
    context = context_for(db, body.investigation_id)
    # Keep prompts minimised: only persisted observation and evidence metadata.
    context.pop("investigation", None)
    result = cited_summary(context, body.task)
    model = "extractive-local"
    status = "completed"
    if settings.ai_enabled and result["citations"]:
        try:
            result["hypotheses"] = await local_model_hypotheses(
                settings.ollama_url,
                settings.ollama_model,
                jsonable_encoder(context),
                body.task,
                {citation["id"] for citation in result["citations"]},
            )
            model = settings.ollama_model
        except (ValueError, KeyError, httpx.HTTPError):
            result["limitations"].append(
                "Modelo opcional indisponível ou resposta sem citações válidas; resumo extrativo preservado."
            )
            status = "fallback"
    run = AIAnalysisRun(
        investigation_id=body.investigation_id,
        model=model,
        status=status,
        prompt=f"task={body.task}; database_context_only; no_mutations",
        response=result,
    )
    db.add(run)
    db.flush()
    audit(db, user, body.investigation_id, "ai.analyzed", run, {"task": body.task, "model": model})
    db.commit()
    return public_record(run)


@router.get("/ai/runs")
def ai_runs(
    db: DB,
    user: Actor,
    investigation_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    investigation_access(db, user, investigation_id)
    return page(db, AIAnalysisRun, investigation_id, limit, offset)


class IndicatorBody(InvestigationBody):
    indicator_type: Literal["ip", "domain", "sha256", "url"]
    value: str = Field(min_length=1, max_length=1024)
    source: str = Field(min_length=1, max_length=150)
    source_url: str = Field(min_length=1, max_length=2048)
    confidence: float = Field(default=0, ge=0, le=1)
    data: dict[str, Any] = Field(default_factory=dict)


@router.get("/threat-indicators")
def indicators(
    db: DB,
    user: Actor,
    investigation_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    investigation_access(db, user, investigation_id)
    return page(db, ThreatIndicator, investigation_id, limit, offset)


@router.post("/threat-indicators", status_code=201)
def indicator_create(body: IndicatorBody, db: DB, user: Actor):
    investigation_access(db, user, body.investigation_id, write=True)
    try:
        value = validate_indicator(body.indicator_type, body.value)
        source_url = safe_source_url(body.source_url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if len(json.dumps(body.data)) > 100_000:
        raise HTTPException(422, "Metadados excedem o limite")
    existing = db.scalar(
        select(ThreatIndicator).where(
            ThreatIndicator.investigation_id == body.investigation_id,
            ThreatIndicator.indicator_type == body.indicator_type,
            ThreatIndicator.value == value,
            ThreatIndicator.source == body.source,
        )
    )
    if existing:
        return public_record(existing)
    record = ThreatIndicator(**{**body.model_dump(), "value": value, "source_url": source_url})
    db.add(record)
    db.flush()
    audit(db, user, body.investigation_id, "indicator.added", record, {"source": body.source})
    db.add(
        Alert(
            investigation_id=body.investigation_id,
            event_type="indicator_added",
            title="Indicador defensivo registrado",
            details={"indicator_id": record.id},
            dedupe_key=f"indicator:{record.id}:added",
        )
    )
    db.commit()
    return public_record(record)


@router.get("/threat-indicators/export")
def indicators_export(db: DB, user: Actor, investigation_id: str, format: Literal["json", "csv"] = "json"):
    investigation_access(db, user, investigation_id)
    records = list(
        db.scalars(
            select(ThreatIndicator)
            .where(ThreatIndicator.investigation_id == investigation_id)
            .order_by(ThreatIndicator.id)
            .limit(10001)
        )
    )
    if len(records) > 10000:
        raise HTTPException(422, "Exportação excede 10.000 indicadores; reduza o escopo")
    rows = [jsonable_encoder(public_record(item)) for item in records]
    content = json.dumps(rows, ensure_ascii=False, indent=2) if format == "json" else csv_export(rows)
    return Response(
        content,
        media_type="application/json" if format == "json" else "text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="indicators.{format}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
