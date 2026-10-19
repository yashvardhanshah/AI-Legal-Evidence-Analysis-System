"""Private cases and evidence; every operation checks current case access."""
from datetime import date
import hashlib
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import Response as ByteResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth import ROLES, audit, current_user, now, user_fields
from app.config import get_settings
from app.library_api import session_dependency
from app.models import AuditLog, AuthSession, Case, CaseMember, Evidence, User
from app.storage import PrivateStorage, StorageError, validate_evidence

router = APIRouter(prefix="/api/v1", tags=["Private workspace"])


@router.get("/workspace/settings")
def workspace_settings(user: User = Depends(current_user)):
    settings = get_settings()
    return {"max_file_bytes": settings.max_file_bytes, "formats": ["pdf", "png", "jpg", "jpeg", "mp4"],
            "video_max_seconds": settings.video_max_seconds, "video_validation_timeout": settings.video_validation_timeout}


def case_scope(user):
    if user.role == "administrator":
        return True
    return or_(Case.owner_id == user.id, exists().where(CaseMember.case_id == Case.id, CaseMember.user_id == user.id))


def authorized_case(db, user, case_id, write=False, manage=False):
    query = select(Case).where(Case.id == case_id, case_scope(user))
    if write or manage:
        query = query.with_for_update()
    case = db.scalar(query)
    if not case:
        raise HTTPException(404, "Case not found")
    owner = case.owner_id == user.id or user.role == "administrator"
    if manage and not owner:
        raise HTTPException(403, "Only the owner or administrator may manage this case")
    if write and not owner and user.role not in {"investigator", "lawyer"}:
        raise HTTPException(403, "This role has read-only access to assigned cases")
    if write and case.status == "archived":
        raise HTTPException(409, "Archived cases are read-only")
    return case


def case_fields(case, user):
    owner = case.owner_id == user.id or user.role == "administrator"
    return {"id": case.id, "reference": case.reference, "title": case.title, "description": case.description,
            "jurisdiction": case.jurisdiction, "owner_id": case.owner_id, "status": case.status,
            "opened_on": case.opened_on, "incident_on": case.incident_on, "archived_at": case.archived_at,
            "created_at": case.created_at, "updated_at": case.updated_at,
            "can_manage": owner, "can_write": case.status == "active" and (owner or user.role in {"investigator", "lawyer"})}


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=10000)
    jurisdiction: str = Field(min_length=1, max_length=255)
    opened_on: date = Field(default_factory=date.today)
    incident_on: date | None = None


class CaseEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=10000)
    jurisdiction: str | None = Field(default=None, min_length=1, max_length=255)
    opened_on: date | None = None
    incident_on: date | None = None

    @model_validator(mode="after")
    def required_values(self):
        if any(name in self.model_fields_set and getattr(self, name) is None for name in ("title", "jurisdiction", "opened_on")):
            raise ValueError("Title, jurisdiction and opened date cannot be null")
        return self


@router.post("/cases", status_code=201)
def create_case(body: CaseCreate, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    case_id = uuid4()
    case = Case(id=case_id, reference="CASE-"+case_id.hex.upper(), owner_id=user.id, **body.model_dump())
    db.add(case)
    db.flush()
    audit(db, user, "case.create", "case", case.id)
    db.commit()
    return case_fields(case, user)


@router.get("/cases")
def list_cases(q: str = Query("", max_length=200), status: str | None = Query(None, pattern="^(active|archived)$"),
               limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
               user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    query = select(Case).where(case_scope(user))
    if q.strip():
        query = query.where(or_(Case.title.icontains(q.strip(), autoescape=True), Case.reference.icontains(q.strip(), autoescape=True), Case.description.icontains(q.strip(), autoescape=True)))
    if status:
        query = query.where(Case.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Case.created_at.desc(), Case.id).offset(offset).limit(limit))
    return {"items": [case_fields(c, user) for c in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/cases/{case_id}")
def get_case(case_id: UUID, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    case = authorized_case(db, user, case_id)
    audit(db, user, "case.read", "case", case.id)
    db.commit()
    return case_fields(case, user)


@router.patch("/cases/{case_id}")
def edit_case(case_id: UUID, body: CaseEdit, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    case = authorized_case(db, user, case_id, write=True)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(case, key, value)
    audit(db, user, "case.update", "case", case.id, fields=sorted(changes))
    db.commit()
    return case_fields(case, user)


@router.post("/cases/{case_id}/archive")
def archive_case(case_id: UUID, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    case = authorized_case(db, user, case_id, manage=True)
    case.status, case.archived_at = "archived", case.archived_at or now()
    audit(db, user, "case.archive", "case", case.id)
    db.commit()
    return case_fields(case, user)


class MemberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)


@router.get("/cases/{case_id}/members")
def members(case_id: UUID, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    authorized_case(db, user, case_id, manage=True)
    rows = db.scalars(select(User).join(CaseMember, CaseMember.user_id == User.id).where(CaseMember.case_id == case_id))
    return {"items": [user_fields(row) for row in rows]}


@router.post("/cases/{case_id}/members", status_code=201)
def add_member(case_id: UUID, body: MemberRequest, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    case = authorized_case(db, user, case_id, manage=True)
    if case.status == "archived":
        raise HTTPException(409, "Archived membership is read-only")
    target = db.scalar(select(User).where(User.email == body.email.strip().lower(), User.is_active.is_(True)))
    if not target:
        raise HTTPException(404, "Registered user not found")
    if target.id == case.owner_id or db.get(CaseMember, (case.id, target.id)):
        raise HTTPException(409, "User already has case access")
    db.add(CaseMember(case_id=case.id, user_id=target.id))
    audit(db, user, "case.member_added", "case", case.id, user_id=str(target.id))
    db.commit()
    return user_fields(target)


@router.delete("/cases/{case_id}/members/{user_id}")
def remove_member(case_id: UUID, user_id: UUID, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    authorized_case(db, user, case_id, manage=True)
    member = db.get(CaseMember, (case_id, user_id))
    if not member:
        raise HTTPException(404, "Member not found")
    db.delete(member)
    audit(db, user, "case.member_removed", "case", case_id, user_id=str(user_id))
    db.commit()
    return {"status": "removed"}


def evidence_fields(row):
    return {"id": row.id, "case_id": row.case_id, "original_filename": row.original_filename,
            "mime_type": row.mime_type, "byte_size": row.byte_size, "sha256": row.sha256,
            "provenance": row.provenance, "uploader_id": row.uploader_id, "captured_on": row.captured_on,
            "created_at": row.created_at}


@router.get("/cases/{case_id}/evidence")
def list_evidence(case_id: UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                  user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    authorized_case(db, user, case_id)
    query = select(Evidence).where(Evidence.case_id == case_id)
    return {"items": [evidence_fields(e) for e in db.scalars(query.order_by(Evidence.created_at.desc(), Evidence.id).offset(offset).limit(limit))],
            "total": db.scalar(select(func.count()).select_from(query.subquery())), "limit": limit, "offset": offset}


@router.post("/cases/{case_id}/evidence", status_code=201)
async def upload(case_id: UUID, request: Request, filename: str = Query(..., min_length=1, max_length=255),
                 provenance: str = Query(..., min_length=3, max_length=2000), captured_on: date | None = None,
                 user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    # Authorize before consuming any request body. A raw binary body avoids
    # unbounded multipart spooling; metadata travels in validated query fields.
    authorized_case(db, user, case_id, write=True)
    settings = get_settings()
    content = bytearray()
    async for chunk in request.stream():
        if len(content)+len(chunk) > settings.max_file_bytes:
            raise HTTPException(413, "Evidence exceeds configured byte limit")
        content.extend(chunk)
    raw = bytes(content)
    if not provenance.strip():
        raise HTTPException(422, "Provenance is required")
    try:
        mime = await run_in_threadpool(validate_evidence, raw, filename, settings.max_file_bytes)
    except StorageError as exc:
        raise HTTPException(422, str(exc)) from exc
    # Re-check mutable session, role and membership after streaming/validation.
    db.refresh(user)
    auth_session = request.state.auth_session
    db.refresh(auth_session)
    if auth_session.revoked_at or auth_session.expires_at <= now() or not user.is_active:
        raise HTTPException(401, "Authentication required")
    case = authorized_case(db, user, case_id, write=True)
    sha = hashlib.sha256(raw).hexdigest()
    if db.scalar(select(Evidence.id).where(Evidence.case_id == case.id, Evidence.sha256 == sha)):
        raise HTTPException(409, "This original already exists in this case")
    try:
        stored = await run_in_threadpool(PrivateStorage(settings.private_root, settings.max_file_bytes).put, raw, "evidence-originals")
    except (OSError, StorageError) as exc:
        raise HTTPException(503, "Private storage unavailable") from exc
    row = Evidence(case_id=case.id, original_filename=filename, mime_type=mime, byte_size=stored.size,
                   sha256=stored.sha256, storage_key=stored.key, provenance=provenance.strip(),
                   uploader_id=user.id, captured_on=captured_on)
    db.add(row)
    db.flush()
    audit(db, user, "evidence.upload", "case", case.id, evidence_id=str(row.id), sha256=row.sha256, byte_size=row.byte_size)
    db.commit()
    return evidence_fields(row)


def authorized_evidence(db, user, case_id, evidence_id):
    authorized_case(db, user, case_id)
    row = db.scalar(select(Evidence).where(Evidence.id == evidence_id, Evidence.case_id == case_id))
    if not row:
        raise HTTPException(404, "Evidence not found")
    return row


@router.get("/cases/{case_id}/evidence/{evidence_id}")
def evidence_detail(case_id: UUID, evidence_id: UUID, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    return evidence_fields(authorized_evidence(db, user, case_id, evidence_id))


@router.get("/cases/{case_id}/evidence/{evidence_id}/download")
def download(case_id: UUID, evidence_id: UUID, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    row = authorized_evidence(db, user, case_id, evidence_id)
    try:
        raw = PrivateStorage(get_settings().private_root).read_verified(row.storage_key, row.sha256)
    except (OSError, StorageError) as exc:
        audit(db, user, "evidence.integrity_failed", "case", case_id, evidence_id=str(row.id))
        db.commit()
        raise HTTPException(409, "Original unavailable or integrity verification failed") from exc
    audit(db, user, "evidence.download", "case", case_id, evidence_id=str(row.id), sha256=row.sha256)
    db.commit()
    from urllib.parse import quote
    return ByteResponse(raw, media_type="application/octet-stream", headers={
        "Content-Disposition": "attachment; filename*=UTF-8''"+quote(row.original_filename, safe=""),
        "X-Content-SHA256": row.sha256, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox; default-src 'none'"})


@router.get("/cases/{case_id}/audit")
def case_audit(case_id: UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
               user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    authorized_case(db, user, case_id, manage=True)
    rows = db.scalars(select(AuditLog).where(AuditLog.resource_type == "case", AuditLog.resource_id == case_id)
                      .order_by(AuditLog.created_at.desc(), AuditLog.id).offset(offset).limit(limit))
    return {"items": [{"id": r.id, "actor": r.actor, "action": r.action, "details": r.details, "created_at": r.created_at} for r in rows]}


class RoleChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str

    @model_validator(mode="after")
    def valid_role(self):
        if self.role not in ROLES:
            raise ValueError("Unknown role")
        return self


@router.patch("/admin/users/{user_id}/role")
def role_change(user_id: UUID, body: RoleChange, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    if user.role != "administrator":
        raise HTTPException(403, "Administrator required")
    if user_id == user.id:
        raise HTTPException(409, "Self role changes are disabled")
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    target.role = body.role
    for session in db.scalars(select(AuthSession).where(AuthSession.user_id == target.id, AuthSession.revoked_at.is_(None))):
        session.revoked_at = now()
    audit(db, user, "user.role_changed", "user", target.id, role=body.role)
    db.commit()
    return user_fields(target)
