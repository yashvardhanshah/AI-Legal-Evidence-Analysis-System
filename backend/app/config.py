from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")
    database_url: str = Field(min_length=1)
    cors_origins: list[str] = ["http://localhost:3000"]
    private_root: Path = Path("../.local/phase2")
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_revision: str = Field(default="1110a243fdf4706b3f48f1d95db1a4f5529b4d41", pattern=r"^[0-9a-f]{40}$")
    max_file_bytes: int = Field(default=20_000_000, gt=0, le=100_000_000)
    max_pdf_pages: int = Field(default=500, gt=0, le=2000)
    ocr_enabled: bool = False
    ocr_timeout_seconds: int = Field(default=60, gt=0, le=300)
    chroma_collection: str = "judgment_passages_minilm_v1"
    jwt_secret: SecretStr | None = None
    jwt_issuer: str = "legal-evidence-local"
    jwt_audience: str = "legal-evidence-workspace"
    access_minutes: int = Field(default=15, ge=1, le=60)
    refresh_days: int = Field(default=7, ge=1, le=30)
    cookie_secure: bool = False  # Set true behind HTTPS before any non-local deployment.
    video_validation_timeout: int = Field(default=20, ge=1, le=60)
    video_max_seconds: int = Field(default=3600, ge=1, le=14400)


@lru_cache
def get_settings() -> Settings:
    return Settings()
