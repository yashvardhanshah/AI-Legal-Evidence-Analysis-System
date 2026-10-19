"""Cookie JWT authentication with revocable sessions and refresh rotation."""
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import hmac
import os
import re
import secrets
from threading import Lock
import time
from uuid import UUID, uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.library_api import session_dependency
from app.models import AuditLog, AuthSession, User
from app.storage import PrivateStorage

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
ACCESS, REFRESH, CSRF = "legal_access", "legal_refresh", "legal_csrf"
ROLES = {"administrator", "investigator", "lawyer", "legal_researcher"}
key_lock = Lock()


def now():
    return datetime.now(timezone.utc)


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def audit(db, user, action, kind, resource_id=None, **details):
    db.add(AuditLog(actor=str(user.id) if user else "anonymous", action=action,
                    resource_type=kind, resource_id=resource_id, details=details))


def password_hash(value: str):
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(value.encode(), salt=salt, n=2**17, r=8, p=1, maxmem=256*1024*1024, dklen=32)
    return f"scrypt$17$8$1${salt.hex()}${key.hex()}"


def password_matches(value: str, encoded: str):
    try:
        scheme, n, r, p, salt, expected = encoded.split("$")
        if (scheme, n, r, p) != ("scrypt", "17", "8", "1"):
            return False
        actual = hashlib.scrypt(value.encode(), salt=bytes.fromhex(salt), n=2**17, r=8, p=1, maxmem=256*1024*1024, dklen=32)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


@lru_cache
def dummy_hash():
    return password_hash(secrets.token_urlsafe(32))


@lru_cache
def signing_key():
    with key_lock:
        return load_signing_key()


def load_signing_key():
    settings = get_settings()
    if settings.jwt_secret:
        value = settings.jwt_secret.get_secret_value()
    else:
        path = PrivateStorage(settings.private_root).path("auth/jwt.key")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w") as stream:
                stream.write(secrets.token_hex(64))
                stream.flush()
                os.fsync(stream.fileno())
        value = path.read_text().strip()
    if len(value.encode()) < 32:
        raise RuntimeError("JWT signing key must contain at least 32 bytes")
    return value


def token(user_id, session_id, kind, expires):
    settings = get_settings()
    return jwt.encode({"sub": str(user_id), "sid": str(session_id), "type": kind,
                       "jti": uuid4().hex, "iat": now(), "nbf": now(), "exp": expires,
                       "iss": settings.jwt_issuer, "aud": settings.jwt_audience}, signing_key(), algorithm="HS256")


def decode(raw, kind):
    try:
        settings = get_settings()
        claims = jwt.decode(raw or "", signing_key(), algorithms=["HS256"], issuer=settings.jwt_issuer,
                            audience=settings.jwt_audience, options={"require": ["sub", "sid", "type", "jti", "iat", "nbf", "exp", "iss", "aud"]})
        if claims["type"] != kind:
            raise ValueError("Wrong token purpose")
        return UUID(claims["sub"]), UUID(claims["sid"])
    except (jwt.InvalidTokenError, ValueError, TypeError) as exc:
        raise HTTPException(401, "Authentication required") from exc


def csrf_check(request: Request, auth_session=None):
    origin = request.headers.get("origin")
    if origin and origin not in get_settings().cors_origins:
        raise HTTPException(403, "Request origin rejected")
    cookie, header = request.cookies.get(CSRF, ""), request.headers.get("x-csrf-token", "")
    if len(cookie) < 32 or not hmac.compare_digest(cookie, header):
        raise HTTPException(403, "CSRF token required")
    if auth_session and not hmac.compare_digest(auth_session.csrf_hash, digest(cookie)):
        raise HTTPException(403, "CSRF session mismatch")


def current_user(request: Request, db: Session = Depends(session_dependency)):
    uid, sid = decode(request.cookies.get(ACCESS), "access")
    auth_session = db.get(AuthSession, sid)
    user = db.get(User, uid)
    if not auth_session or auth_session.user_id != uid or auth_session.revoked_at or auth_session.expires_at <= now() or not user or not user.is_active:
        raise HTTPException(401, "Authentication required")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf_check(request, auth_session)
    request.state.auth_session = auth_session
    return user


def user_fields(user):
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role}


def set_cookie(response, name, value, age, http_only=True):
    response.set_cookie(name, value, max_age=age, httponly=http_only, secure=get_settings().cookie_secure,
                        samesite="strict", path="/")


def issue(response, db, user, auth_session=None):
    settings = get_settings()
    csrf = secrets.token_urlsafe(32)
    if auth_session is None:
        auth_session = AuthSession(id=uuid4(), user_id=user.id, expires_at=now()+timedelta(days=settings.refresh_days))
        db.add(auth_session)
    refresh = token(user.id, auth_session.id, "refresh", auth_session.expires_at)
    auth_session.refresh_hash, auth_session.csrf_hash = digest(refresh), digest(csrf)
    remaining = max(0, int((auth_session.expires_at-now()).total_seconds()))
    set_cookie(response, ACCESS, token(user.id, auth_session.id, "access", min(now()+timedelta(minutes=settings.access_minutes), auth_session.expires_at)), min(settings.access_minutes*60, remaining))
    set_cookie(response, REFRESH, refresh, remaining)
    set_cookie(response, CSRF, csrf, remaining, False)
    response.headers["Cache-Control"] = "no-store"
    return auth_session


class Register(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def email_format(cls, value):
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", value):
            raise ValueError("Provide a valid email address")
        return value.lower()

    @field_validator("display_name")
    @classmethod
    def valid_name(cls, value):
        if not value.strip():
            raise ValueError("Display name is required")
        return value.strip()

    @field_validator("password")
    @classmethod
    def password_strength(cls, value):
        if len(set(value)) < 6 or value.lower() in {"password123456", "123456789012", "qwerty12345678"}:
            raise ValueError("Use a strong password or passphrase")
        return value


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class RateLimiter:
    """Bounded, per-process defence for this single-worker local deployment."""
    def __init__(self):
        self.entries = defaultdict(deque)
        self.lock = Lock()

    def check(self, request, name, limit, period):
        key = (request.client.host if request.client else "unknown", name)
        clock = time.monotonic()
        with self.lock:
            if len(self.entries) > 10000:
                self.entries = defaultdict(deque, {k: v for k, v in self.entries.items() if v and clock-v[-1] < 3600})
            queue = self.entries[key]
            while queue and clock-queue[0] >= period:
                queue.popleft()
            if len(queue) >= limit:
                raise HTTPException(429, "Too many attempts; try again later", headers={"Retry-After": str(period)})
            queue.append(clock)


limiter = RateLimiter()


@router.get("/csrf")
def csrf_token(response: Response, request: Request):
    # Preserve the authenticated session's CSRF token; do not rotate it here.
    value = request.cookies.get(CSRF) or secrets.token_urlsafe(32)
    set_cookie(response, CSRF, value, get_settings().refresh_days*86400, False)
    response.headers["Cache-Control"] = "no-store"
    return {"csrf_token": value}


@router.post("/register", status_code=201)
def register(body: Register, request: Request, db: Session = Depends(session_dependency)):
    csrf_check(request)
    limiter.check(request, "register", 10, 3600)
    user = User(email=body.email, display_name=body.display_name, password_hash=password_hash(body.password), role="legal_researcher")
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Registration unavailable for this address") from exc
    audit(db, user, "auth.register", "user", user.id)
    db.commit()
    return user_fields(user)


@router.post("/login")
def login(body: Login, request: Request, response: Response, db: Session = Depends(session_dependency)):
    csrf_check(request)
    limiter.check(request, "login", 30, 60)
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()).with_for_update())
    valid = password_matches(body.password, user.password_hash if user else dummy_hash())
    if not user or not user.is_active or not valid or (user.locked_until and user.locked_until > now()):
        if user:
            user.failed_logins += 1
            if user.failed_logins >= 5:
                user.locked_until = now()+timedelta(minutes=15)
        audit(db, user, "auth.login_failed", "user", user.id if user else None)
        db.commit()
        raise HTTPException(401, "Invalid credentials or temporarily locked account")
    user.failed_logins, user.locked_until = 0, None
    session = issue(response, db, user)
    audit(db, user, "auth.login", "session", session.id)
    db.commit()
    return {"user": user_fields(user), "expires_in": get_settings().access_minutes*60}


@router.get("/me")
def me(response: Response, user: User = Depends(current_user)):
    response.headers["Cache-Control"] = "no-store"
    return user_fields(user)


@router.post("/refresh")
def refresh(request: Request, response: Response, db: Session = Depends(session_dependency)):
    uid, sid = decode(request.cookies.get(REFRESH), "refresh")
    session = db.scalar(select(AuthSession).where(AuthSession.id == sid).with_for_update())
    if not session or session.user_id != uid or session.revoked_at or session.expires_at <= now():
        raise HTTPException(401, "Authentication required")
    csrf_check(request, session)
    if not hmac.compare_digest(session.refresh_hash, digest(request.cookies.get(REFRESH, ""))):
        session.revoked_at = now()
        audit(db, None, "auth.refresh_replay", "session", sid)
        db.commit()
        raise HTTPException(401, "Refresh token replay; session revoked")
    user = db.get(User, uid)
    if not user or not user.is_active:
        raise HTTPException(401, "Authentication required")
    issue(response, db, user, session)
    audit(db, user, "auth.refresh", "session", sid)
    db.commit()
    return {"user": user_fields(user), "expires_in": get_settings().access_minutes*60}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(session_dependency)):
    # A valid refresh cookie lets logout work even after access-token expiry.
    uid, sid = decode(request.cookies.get(REFRESH), "refresh")
    session = db.scalar(select(AuthSession).where(AuthSession.id == sid).with_for_update())
    if not session or session.user_id != uid:
        raise HTTPException(401, "Authentication required")
    csrf_check(request, session)
    session.revoked_at = now()
    audit(db, db.get(User, uid), "auth.logout", "session", sid)
    db.commit()
    for name in (ACCESS, REFRESH, CSRF):
        response.delete_cookie(name, path="/", secure=get_settings().cookie_secure, httponly=name != CSRF, samesite="strict")
    return {"status": "logged_out"}
