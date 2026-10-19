import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.database import get_engine
from app.models import SystemMetadata
from app.library_api import router
from app.auth import router as auth_router
from app.case_api import router as case_router
from app.security_middleware import RequestSafety

logger = logging.getLogger(__name__)
app = FastAPI(title="AI Legal Evidence Analysis System", version="0.3.0")
app.add_middleware(RequestSafety)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.include_router(router)
app.include_router(auth_router)
app.include_router(case_router)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Pydantic errors can otherwise echo submitted passwords or private bodies.
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]} for error in exc.errors()]})


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    logger.warning("Database request failed (%s)", type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "Database service unavailable"})


@app.get("/api/v1/health/live")
def live():
    return {"status": "ok", "service": "legal-evidence-api"}


@app.get("/api/v1/health/ready")
def ready():
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            phase = connection.execute(
                select(SystemMetadata.value).where(SystemMetadata.key == "development_phase")
            ).scalar_one()
            if revision not in {"0001_foundation", "0002_legal_data", "0003_private_workspace"} or phase != "1":
                return JSONResponse(status_code=503, content={"status": "unavailable", "database": "schema_mismatch"})
    except SQLAlchemyError as exc:
        # Do not expose connection strings or raw driver messages.
        logger.warning("Database readiness failed (%s)", type(exc).__name__)
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "unavailable"})
    return {"status": "ok", "database": "connected", "migration": revision, "phase": phase}
