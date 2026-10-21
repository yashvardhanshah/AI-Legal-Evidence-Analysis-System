# Architecture

Phase 7 adds deterministic `report_sources.py` snapshots, local `report_pdf.py`, `report_jobs.py` and case-private `report_api.py`. The fenced worker gains `--kind case_report` and an isolated report-worker. Private immutable PDF/JSON outputs retain original/derived/model/judgment references; append-only reviewer decisions are external and hash bound. No LLM or new inference runs. See [PHASE7_DESIGN.md](docs/PHASE7_DESIGN.md).

Phase 6 adds `legal_retrieval.py` (filtered public source retrieval), operator-only `statute_ingestion.py` (rights-gated exact-span versions and a separate statute index), `research_api.py` and `research_jobs.py` (case-private source-bound research/review), and the existing worker's `--kind legal_research` dispatch. No new dependency or LLM is used. Queries are exact token windows from selected completed extraction spans or explicitly confirmed human input. Original files and extraction artifacts are hash-verified; publication retains exact input/query/source references. All earlier collections and analysis history are preserved. See [PHASE6_DESIGN.md](docs/PHASE6_DESIGN.md).

Phase 5 adds an isolated `visual-worker` using the existing worker's `--kind visual_analysis` dispatch, private case-authorized `visual_api.py`, immutable `visual_jobs.py` publication and pinned local `visual_inference.py`/`visual_model.py`. Existing document worker behavior remains the default. OpenCV sequentially decodes MP4s, samples actual presentation timestamps and applies YOLOX to images/samples; private source/annotated PNGs retain source/model/frame provenance. No facial identity, re-identification, continuous tracking or crime inference is introduced. See [PHASE5_DESIGN.md](docs/PHASE5_DESIGN.md).

Phase 4 adds `analysis_api.py` (case-authorized enqueue/results), `analysis_worker.py` (separate durable SQL worker and fenced child processes), `analysis_jobs.py` (attempt/provenance/publishing), `analysis_extraction.py` (embedded text and actual TSV OCR), `analysis_nlp.py` (offline NER and literal spans), and `ner_model.py` (approved acquisition/integrity). Original evidence remains immutable; derived JSON, exact page text, models and source-linked candidates are tracked separately. Chroma and existing public research routes are unchanged. See [PHASE4_DESIGN.md](docs/PHASE4_DESIGN.md).

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

The original database volume is retained. Only the backend mounts ignored `.local/phase2` as `/private_data`. Originals, model snapshots, receipts and Chroma survive container restarts. Phase 3 adds authorized case/evidence routes below. Windows ACLs inherit workspace access; review deployment host ACLs before confidential evidence. Celery/Redis remain deferred: bounded resumable jobs run outside request handlers as operator commands, with states persisted in SQL and writes serialized by advisory lock.

## Phase 3 private workspace

Browser login/register/case pages -> same-origin streaming Next.js `/api/backend/*` proxy -> FastAPI cookie JWT + CSRF checks -> current PostgreSQL user/session -> owner/member/role case scope -> SQL metadata/audit and immutable private originals. Public legal research routes retain the Phase 2 policy. No dataset or embedding pipeline is recreated.

`auth.py` owns password hashing, JWT purposes/expiry/rotation, session revocation, CSRF and local throttling. `case_api.py` centralizes case authorization before every private operation; `security_middleware.py` limits actual request bodies and disables private response caching. `manage_users.py` is a local-only first-administrator operator command. `verify_phase3.py` performs an opt-in real HTTP flow using an existing licensed judgment and retains its credentials only in private storage. Original evidence is served solely through an authorized, hash-verified attachment response. See [SECURITY.md](docs/SECURITY.md) for the exact role matrix and deployment limitations.

Chroma upserts precede SQL index markers; a failed batch can repeat its deterministic IDs. Queries suppress entries without matching committed SQL records and revision/hash. No destructive reset is used.
