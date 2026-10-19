import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.database import get_engine
from app.models import SystemMetadata

logger = logging.getLogger(__name__)
app = FastAPI(title="AI Legal Evidence Analysis System", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)


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
            if revision != "0001_foundation" or phase != "1":
                return JSONResponse(status_code=503, content={"status": "unavailable", "database": "schema_mismatch"})
    except SQLAlchemyError as exc:
        # Do not expose connection strings or raw driver messages.
        logger.warning("Database readiness failed (%s)", type(exc).__name__)
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "unavailable"})
    return {"status": "ok", "database": "connected", "migration": revision, "phase": phase}
