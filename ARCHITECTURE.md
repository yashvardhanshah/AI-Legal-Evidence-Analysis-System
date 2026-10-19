# Architecture

```text
Browser :3000
  -> Next.js App Router / responsive foundation dashboard
  -> same-origin GET /api/system (Next.js server)
  -> FastAPI :8000 /api/v1/health/ready
  -> SQLAlchemy + psycopg
  -> PostgreSQL 18 / installation metadata + Alembic revision
```

`frontend/` contains React, TypeScript and Tailwind. The server-only API base URL defaults to local FastAPI and resolves to `backend` inside Compose. Requests have timeouts, disable caching, and return sanitized failures.

`backend/app/` separates configuration, database access, models and HTTP routes. Configuration loads environment variables; secrets are absent from committed source. Connection pools validate existing connections. Readiness checks a real SQL query, migration revision and persisted installation metadata. Liveness is independent of database availability. Alembic is an explicit one-shot startup service; application startup never creates tables implicitly.

Compose binds published ports to loopback. PostgreSQL data lives in a named volume. Application containers run as non-root users. There are no uploads, public file routes, domain records or credentials seeded in Phase 1. The `.env` is deliberately excluded from image build contexts.

Future boundaries: authenticated API with role and case authorization; immutable original files in private object/local storage; derived artifacts stored separately; audited background jobs through Celery/Redis; Chroma passage vectors referencing PostgreSQL rows; provider-configurable source-grounded LLM workflows. No models, dataset downloads or paid calls occur in Phase 1.
