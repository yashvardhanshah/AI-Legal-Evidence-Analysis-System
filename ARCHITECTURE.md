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

Phase 1 performed no model downloads, dataset ingestion or paid calls. Phase 2 below implements private originals and persistent Chroma passage vectors referencing PostgreSQL rows. Authentication, role/case authorization, Celery/Redis orchestration and source-grounded LLM/report workflows remain later-phase boundaries.


## Phase 2 public legal infrastructure

Reviewed publisher/license -> bounded approval-hashed manifest -> conditional HTTPS PDF/JSON acquisition -> SHA-256 originals/receipts -> extraction or necessary local OCR -> tokenizer-aware page chunks in PostgreSQL -> offline CPU embeddings -> persistent cosine Chroma -> SQL provenance join -> read-only public library API.

`sources.py` handles allowlisted public access and metadata; `storage.py` handles immutable files and safe paths; `documents.py` extracts and chunks; `ingestion.py` persists source versions, passages, jobs and audit events; `vectors.py` isolates explicit model acquisition, offline inference and index reconciliation; `library_api.py` exposes the public corpus; `cli.py` is the trusted operator entry point. Ingestion is never triggered from HTTP.

The original database volume is retained. Only the backend mounts ignored `.local/phase2` as `/private_data`. Originals, model snapshots, receipts and Chroma survive container restarts. Cases and evidence have no routes before Phase 3 authorization. Windows ACLs inherit workspace access; review deployment host ACLs before confidential evidence. Celery/Redis remain deferred: bounded resumable jobs run outside request handlers as operator commands, with states persisted in SQL and writes serialized by advisory lock.

Chroma upserts precede SQL index markers; a failed batch can repeat its deterministic IDs. Queries suppress entries without matching committed SQL records and revision/hash. No destructive reset is used.
