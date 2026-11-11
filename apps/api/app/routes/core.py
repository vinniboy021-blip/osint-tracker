from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth import (
    audit,
    current_user,
    hash_password,
    investigation_access,
    owner_access,
    require_admin,
    user_dict,
)
from app.db import get_db
from app.models import (
    Alert,
    AuditLog,
    CollectionJob,
    Connector,
    Entity,
    Investigation,
    InvestigationMember,
    Observation,
    ThreatIndicator,
    Timeline,
    User,
    WorkspaceItem,
)
from app.notifications import deliver

router = APIRouter(tags=["Núcleo"])


def dump(x):
    return {c.name: getattr(x, c.name) for c in x.__table__.columns}


def page(db, q, skip=0, limit=50):
    limit = min(max(limit, 1), 200)
    return {
        "items": [dump(x) for x in db.scalars(q.offset(skip).limit(limit)).all()],
        "total": db.scalar(select(func.count()).select_from(q.subquery())) or 0,
    }


def allowed_investigations(db: Session, user: User):
    """Return the investigation scope visible to a user for aggregate/list endpoints."""
    if user.role == "admin":
        return select(Investigation.id)
    membership = select(InvestigationMember.investigation_id).where(InvestigationMember.user_id == user.id)
    return select(Investigation.id).where(
        or_(Investigation.owner_id == user.id, Investigation.id.in_(membership))
    )


class InvestigationIn(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    objective: str = ""
    scope: str = ""


class EntityIn(BaseModel):
    investigation_id: str
    type: str
    canonical_value: str
    label: str | None = None
    attributes: dict[str, Any] = {}


class WorkspaceIn(BaseModel):
    investigation_id: str
    kind: str
    label: str
    content: str = ""
    status: str = "open"


class UserIn(BaseModel):
    email: str
    password: str = Field(min_length=12)
    role: str = "analyst"


class MemberIn(BaseModel):
    user_id: str | None = None
    email: str | None = None
    role: str = "viewer"

    def resolve_identifier(self) -> str:
        if bool(self.user_id) == bool(self.email):
            raise ValueError("Informe user_id ou email")
        return self.user_id or self.email or ""


@router.get("/health/live")
def live():
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(select(1))
        return {"status": "ready", "database": "ok"}
    except Exception as exc:
        raise HTTPException(503, "Banco indisponível") from exc


@router.get("/metrics")
def metrics():
    return {"status": "ok"}


@router.get("/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    allowed = allowed_investigations(db, user)
    return {
        "investigations": db.scalar(select(func.count()).select_from(allowed.subquery())) or 0,
        "observations": db.scalar(
            select(func.count()).select_from(Observation).where(Observation.investigation_id.in_(allowed))
        )
        or 0,
        "alerts": db.scalar(
            select(func.count())
            .select_from(Alert)
            .where(Alert.is_read.is_(False), Alert.investigation_id.in_(allowed))
        )
        or 0,
        "entities": db.scalar(
            select(func.count()).select_from(Entity).where(Entity.investigation_id.in_(allowed))
        )
        or 0,
        "jobs_failed": db.scalar(
            select(func.count())
            .select_from(CollectionJob)
            .where(
                CollectionJob.status.in_(["failed", "dead_letter"]),
                CollectionJob.investigation_id.in_(allowed),
            )
        )
        or 0,
        "connectors_healthy": db.scalar(
            select(func.count()).select_from(Connector).where(Connector.health == "healthy")
        )
        or 0,
    }


@router.get("/search")
def global_search(
    q: str,
    investigation_id: str | None = None,
    limit: int = 50,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Search only persisted, investigation-scoped records; no remote enumeration."""
    if len(q.strip()) < 2:
        raise HTTPException(422, "A busca exige pelo menos dois caracteres")
    term = f"%{q.strip()}%"
    if investigation_id:
        investigation_access(db, user, investigation_id)
        scope = investigation_id
    else:
        scope = None
    entity_query = select(Entity).where(Entity.canonical_value.ilike(term) | Entity.label.ilike(term))
    observation_query = select(Observation).where(
        Observation.source_name.ilike(term) | Observation.source_url.ilike(term)
    )
    indicator_query = select(ThreatIndicator).where(
        ThreatIndicator.value.ilike(term) | ThreatIndicator.source.ilike(term)
    )
    if scope:
        entity_query = entity_query.where(Entity.investigation_id == scope)
        observation_query = observation_query.where(Observation.investigation_id == scope)
        indicator_query = indicator_query.where(ThreatIndicator.investigation_id == scope)
    else:
        entity_query = entity_query.where(Entity.investigation_id.in_(allowed_investigations(db, user)))
        observation_query = observation_query.where(
            Observation.investigation_id.in_(allowed_investigations(db, user))
        )
        indicator_query = indicator_query.where(
            ThreatIndicator.investigation_id.in_(allowed_investigations(db, user))
        )
    return {
        "entities": [dump(x) for x in db.scalars(entity_query.limit(limit))],
        "observations": [dump(x) for x in db.scalars(observation_query.limit(limit))],
        "threat_indicators": [dump(x) for x in db.scalars(indicator_query.limit(limit))],
    }


@router.get("/investigations")
def investigations(
    skip: int = 0, limit: int = 50, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    q = select(Investigation)
    if user.role != "admin":
        q = q.where(Investigation.id.in_(allowed_investigations(db, user)))
    return page(db, q, skip, limit)


@router.post("/investigations", status_code=201)
def create_investigation(
    body: InvestigationIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    i = Investigation(**body.model_dump(), owner_id=user.id)
    db.add(i)
    db.flush()
    audit(db, user, "investigation.create", "investigation", i.id, i.id)
    db.commit()
    return dump(i)


@router.get("/investigations/{id}")
def get_investigation(id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return dump(investigation_access(db, user, id))


@router.get("/investigations/{id}/members")
def investigation_members(id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    investigation_access(db, user, id)
    members = db.scalars(select(InvestigationMember).where(InvestigationMember.investigation_id == id)).all()
    owner = db.scalar(select(Investigation).where(Investigation.id == id))
    result = []
    for member in members:
        member_user = db.get(User, member.user_id)
        if member_user:
            result.append({**dump(member), "user": user_dict(member_user)})
    if owner and not any(member["user_id"] == owner.owner_id for member in result):
        owner_user = db.get(User, owner.owner_id)
        if owner_user:
            result.insert(
                0,
                {
                    "id": None,
                    "investigation_id": id,
                    "user_id": owner.owner_id,
                    "role": "owner",
                    "user": user_dict(owner_user),
                },
            )
    return {"items": result, "total": len(result)}


@router.post("/investigations/{id}/members", status_code=201)
def add_investigation_member(
    id: str, body: MemberIn, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    investigation = owner_access(db, user, id)
    if body.role not in {"editor", "viewer"}:
        raise HTTPException(422, "Papel de investigação inválido")
    try:
        identifier = body.resolve_identifier()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    target = db.scalar(
        select(User).where(User.id == identifier)
    ) if body.user_id else db.scalar(select(User).where(User.email == identifier.lower()))
    if not target or not target.is_active:
        raise HTTPException(404, "Usuário não encontrado")
    if target.id == investigation.owner_id:
        raise HTTPException(409, "O responsável já possui papel de proprietário")
    member = db.scalar(
        select(InvestigationMember).where(
            InvestigationMember.investigation_id == id, InvestigationMember.user_id == target.id
        )
    )
    if member:
        member.role = body.role
    else:
        member = InvestigationMember(investigation_id=id, user_id=target.id, role=body.role)
        db.add(member)
    audit(db, user, "investigation.member.upsert", "investigation_member", member.id, id)
    db.commit()
    return {**dump(member), "user": user_dict(target)}


@router.delete("/investigations/{id}/members/{member_user_id}", status_code=204)
def remove_investigation_member(
    id: str, member_user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    owner_access(db, user, id)
    member = db.scalar(
        select(InvestigationMember).where(
            InvestigationMember.investigation_id == id, InvestigationMember.user_id == member_user_id
        )
    )
    if not member:
        raise HTTPException(404, "Membro não encontrado")
    db.delete(member)
    audit(db, user, "investigation.member.remove", "investigation_member", member.id, id)
    db.commit()


@router.post("/entities", status_code=201)
def create_entity(body: EntityIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    investigation_access(db, user, body.investigation_id, True)
    values = body.model_dump()
    values["label"] = values.get("label") or values["canonical_value"]
    e = Entity(**values)
    db.add(e)
    db.commit()
    return dump(e)


@router.get("/entities")
def entities(
    investigation_id: str,
    skip: int = 0,
    limit: int = 50,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    investigation_access(db, user, investigation_id)
    return page(db, select(Entity).where(Entity.investigation_id == investigation_id), skip, limit)


@router.get("/observations")
def observations(
    investigation_id: str,
    skip: int = 0,
    limit: int = 50,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    investigation_access(db, user, investigation_id)
    return page(
        db,
        select(Observation)
        .where(Observation.investigation_id == investigation_id)
        .order_by(Observation.collected_at.desc()),
        skip,
        limit,
    )


@router.get("/timeline")
def timeline(
    investigation_id: str,
    skip: int = 0,
    limit: int = 50,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    investigation_access(db, user, investigation_id)
    return page(
        db,
        select(Timeline)
        .where(Timeline.investigation_id == investigation_id)
        .order_by(Timeline.created_at.desc()),
        skip,
        limit,
    )


@router.get("/alerts")
def alerts(
    investigation_id: str | None = None,
    skip: int = 0,
    limit: int = 50,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    q = select(Alert)
    if investigation_id:
        investigation_access(db, user, investigation_id)
        q = q.where(Alert.investigation_id == investigation_id)
    else:
        q = q.where(Alert.investigation_id.in_(allowed_investigations(db, user)))
    return page(db, q.order_by(Alert.created_at.desc()), skip, limit)


@router.patch("/alerts/{id}")
def mark_alert(id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Alert, id)
    if not a:
        raise HTTPException(404, "Alerta não encontrado")
    investigation_access(db, user, a.investigation_id, True)
    a.is_read = True
    db.commit()
    return dump(a)


@router.post("/alerts/{id}/deliver")
def deliver_alert(
    id: str,
    recipient: EmailStr = "",
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    alert = db.get(Alert, id)
    if not alert:
        raise HTTPException(404, "Alerta não encontrado")
    investigation_access(db, user, alert.investigation_id, write=True)
    try:
        result = deliver(alert, str(recipient) if recipient else "")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "Falha na entrega da notificação") from exc
    return {"alert_id": alert.id, "delivery": result}


@router.post("/workspace-items", status_code=201)
def workspace(body: WorkspaceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    investigation_access(db, user, body.investigation_id, True)
    x = WorkspaceItem(**body.model_dump())
    db.add(x)
    db.commit()
    return dump(x)


@router.get("/workspace-items")
def workspaces(investigation_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    investigation_access(db, user, investigation_id)
    return page(db, select(WorkspaceItem).where(WorkspaceItem.investigation_id == investigation_id))


@router.get("/audit")
def audit_log(
    investigation_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    q = select(AuditLog).order_by(AuditLog.created_at.desc())
    if investigation_id:
        investigation_access(db, user, investigation_id)
        q = q.where(AuditLog.investigation_id == investigation_id)
    else:
        q = q.where(AuditLog.investigation_id.in_(allowed_investigations(db, user)))
    return page(db, q)


@router.get("/admin/users")
def users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    records = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return {"items": [user_dict(record) for record in records], "total": len(records)}


@router.post("/admin/users", status_code=201)
def create_user(body: UserIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    if body.role not in {"admin", "analyst", "viewer"}:
        raise HTTPException(422, "Papel inválido")
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "E-mail já cadastrado")
    u = User(email=body.email.lower(), password_hash=hash_password(body.password), role=body.role)
    db.add(u)
    db.commit()
    return {"id": u.id, "email": u.email, "role": u.role, "is_active": u.is_active}


@router.get("/admin/connectors")
def connectors(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return page(db, select(Connector))
