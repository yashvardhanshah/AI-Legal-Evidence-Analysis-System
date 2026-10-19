# AI Legal Evidence Analysis System

Academic investigation and legal research decision support for India. Phases 1 and 2 provide the application stack, 50 licensed public judgments and 3,834 persisted embeddings. Phase 3 adds cookie JWT authentication, case ownership/sharing, role checks, private evidence upload/download and audit logs. Keep services on loopback. See [the access policy](docs/SECURITY.md) before using private evidence.

## Requirements

Node.js 22+, Python 3.13, Git, and a running Docker Desktop Linux-container engine with Docker Compose. Native PostgreSQL is optional. Dependency versions are captured in `frontend/package-lock.json` and `backend/requirements.lock`.

## Start with Docker (PowerShell, repository root)

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edit .env: set POSTGRES_PASSWORD to a fresh random alphanumeric value.
# Set DATABASE_URL to use that password for native backend commands.
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Open http://localhost:3000 and http://localhost:8000/docs. PostgreSQL is bound to `127.0.0.1:5433`; existing local PostgreSQL on 5432 is unaffected. Docker uses the individual POSTGRES_* values; DATABASE_URL is for native development. If a generated local `.env` already exists, retain it rather than replacing it.

```powershell
docker compose logs --tail 100 backend migrate frontend
docker compose exec backend python -m pytest -q
docker compose exec -e RUN_DB_TESTS=1 backend python -m pytest -q
docker compose down
```

`down` preserves the database volume. Do not use `down -v` unless explicitly authorized to destroy that local database.

## Native development with containerized PostgreSQL

```powershell
docker compose up -d db
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.lock
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-phase3.lock
Set-Location backend
.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

In another terminal:

```powershell
Set-Location frontend
npm ci
# Native default is http://127.0.0.1:8000; set API_BASE_URL here to override it.
npm run dev
```

The frontend server proxies readiness checks; no secrets enter browser environment variables. See [TESTING.md](TESTING.md) for checks and measured results, [ARCHITECTURE.md](ARCHITECTURE.md), [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md), [SOURCES.md](SOURCES.md), [AI_MODELS.md](AI_MODELS.md), [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), and [docs/API.md](docs/API.md).

### Existing native fallback from Phase 1 verification

Initial Docker registry pulls failed during verification. An isolated PostgreSQL 18 cluster was initialized at ignored `.local/pgdata`, using the password in the ignored root `.env`. It uses port 5433 and does not alter the existing system PostgreSQL service on 5432. To reuse this cluster after stopping it:

```powershell
# Repository root; skip start if already running.
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D .local/pgdata -l .local/postgres.log -o '-p 5433 -h 127.0.0.1' -w start
# Then start backend and frontend using the native commands above (skip docker db).
# Stop the isolated cluster before starting the Docker db on the same port:
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D .local/pgdata -w stop
```

This fallback cluster is local runtime state and is not portable repository content. New clones should use the documented Compose setup.

The native fallback cluster retains only the earlier Phase 1 verification state. The current Phase 2 corpus lives in the Compose PostgreSQL volume. Use that database for Phase 2; switching databases does not transfer provenance rows or their vector IDs.

If normal pulls fail with Docker Hub connection EOF errors, the standard image was successfully fetched through BuildKit with this command before retrying Compose:

```powershell
'FROM postgres:18' | docker build --tag postgres:18 -
```

## Version control

Origin: https://github.com/yashvardhanshah/AI-Legal-Evidence-Analysis-System.git, branch `main`. GitHub had no refs at the initial read on 2026-10-19. Phase 1 has been reviewed by the project owner. Every commit and push requires explicit user approval; recheck remote refs before pushing. `.gitignore` is a safeguard, not a replacement for reviewing every staged file. Keep original evidence, datasets, models, credentials and database backups outside Git.

Implementation references: [Next.js installation](https://nextjs.org/docs/app/getting-started/installation), [FastAPI containers](https://fastapi.tiangolo.com/deployment/docker/), [Compose service dependencies](https://docs.docker.com/compose/how-tos/startup-order/).

## Phase 2 operator workflow

Use Docker for CPU inference, Chroma and Tesseract; allow up to 4 GB of disk including images. All downloads are explicit operator commands after approval. Model loads and health checks never download files. No paid service is required.

The first CPU dependency image is about **1.79 GB**; build/export/unpack can be silent for several minutes. Backend and migrations share one image. If the default exporter is unusually slow, this locally verified sequence reuses dependency caches, exports without compression, and never pushes an image:

```powershell
docker buildx build --output 'type=image,name=legal-evidence-backend,compression=uncompressed,push=false,store=true' ./backend
docker compose build frontend
docker compose up --no-build --wait --wait-timeout 180
```

The exact tested Linux CPU dependency snapshot is `backend/requirements-ml.lock`; native development instructions above install core dependencies only. Use Docker for the full ML/OCR test suite. A native Windows fallback was assessed through package metadata only and was not installed.

```powershell
docker compose exec -T backend python -m app.cli register-sources
docker compose exec -T backend python -m app.cli plan-supreme --year 1951 --limit 50 --output /private_data/plans/supreme-1951-50.json
$batch = Get-Content .local/phase2/plans/supreme-1951-50.json -Raw | ConvertFrom-Json
$batch.total_bytes
$batch.documents.Count
$manifestHash = (Get-FileHash .local/phase2/plans/supreme-1951-50.json -Algorithm SHA256).Hash.ToLower()
# Review the manifest and obtain approval for dataset/model downloads first.
docker compose exec -T backend python -m app.cli download-model --approved-bytes 92000000
docker compose exec -T backend python -m app.cli ingest --manifest /private_data/plans/supreme-1951-50.json --approved-sha256 $manifestHash --max-total-bytes 45000000
docker compose exec -T backend python -m app.cli index
docker compose exec -T backend python -m app.cli stats
docker compose exec -T backend python -m app.cli search 'fundamental rights and equality before the law' --limit 3
```

The initial approved plan selects the first 50 English PDF keys with matching metadata in the publisher's `year=1951` partition: **44,893,069 bytes** including metadata. Some identifiers begin with 1952; partition year is not treated as a judgment date. Initial plan SHA-256: `58fd46d2e7a7188cd0b0eedc8bf29fab5e1f6d9f281b1282ee4a7b7a9dbbdbd0`. Regenerating a plan changes its timestamp/hash; use the new actual hash after review. See SOURCES.md for rights and attribution.

Rerunning ingestion skips unchanged records. Download receipts allow retries without redownloading verified originals. For a failed/interrupted job, add `--retry-job <job-id>` with the same manifest and approval hash. A changed ETag requires version review; originals are never overwritten. PostgreSQL advisory locks serialize operator writers. Indexing upserts deterministic passage IDs and resumes missing embeddings without duplicating vectors.

```powershell
$query = @{query='fundamental rights and equality before the law'; limit=3} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/search/judgments -ContentType application/json -Body $query
Invoke-RestMethod http://localhost:8000/api/v1/dataset-sources
Invoke-RestMethod http://localhost:8000/api/v1/ingestion-jobs
Invoke-RestMethod 'http://localhost:8000/api/v1/judgments?limit=5'
Invoke-RestMethod 'http://localhost:8000/api/v1/legal-provisions?q=equality'
docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_CORPUS_TESTS=1 backend python -m pytest -q -p no:cacheprovider
backend/.venv/Scripts/python.exe scripts/smoke.py
```

Results contain actual SQL passages, source URLs, available dates and cosine **distance** (lower is closer). They do not certify legal applicability or ranking quality. The historical English sample is not representative of modern criminal law.

Ignored `.local/phase2` is mounted only into the backend as `/private_data`, with `originals/`, `metadata/`, `receipts/`, `plans/`, `models/<revision>/` and `chroma/`. Evidence originals and derived files use separate namespaces. Nothing is served as static files. Windows ACLs inherit the development workspace; review host access before introducing confidential evidence.

Private evidence should use the authenticated case upload page/API. The retained local-operator `import-evidence --case-id <existing-id> --uploader-id <active-user-id> --file <authorized-file> --provenance <description>` also enforces the supplied user's case/role access and records that uploader; it requires trusted database operator access. PDF/PNG/JPG/JPEG/MP4 validation is shared with HTTP uploads. `import-provision --manifest <reviewed-manifest>` requires verified authoritative source rights, an exact PDF page passage, document SHA-256, explicit act/version/section and reviewer. Missing statutes stay empty; no sections or crosswalks are invented. Neither command bypasses the source/format gates.

## Phase 3 workspace and verification

Open http://localhost:3000/register, create your account, then log in at http://localhost:3000/login. Create a case at `/cases/new`, open its detail page, and upload a genuine authorized original with provenance. Uploaded/downloaded SHA-256 values are compared in the browser; case sharing and audit events are available to the owner. New registrations cannot choose privileged roles. See [SECURITY.md](docs/SECURITY.md) for first-administrator bootstrap and the exact access matrix.

For the existing installation (retain `.env`, the volume and `.local/phase2`):

```powershell
docker compose build backend frontend
docker compose up --no-build --wait --wait-timeout 180
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
docker compose exec -T backend python -m pip check
docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_CORPUS_TESTS=1 backend python -m pytest -q -p no:cacheprovider
backend/.venv/Scripts/python.exe scripts/smoke.py
```

Native MP4 validation additionally requires `ffmpeg` and `ffprobe` on PATH; Compose installs them. The JWT key, evidence originals and opt-in flow receipt live under the existing ignored private mount. The following operator command creates an explicitly labeled verification account/case and uploads an unchanged copy of one already ingested CC BY 4.0 judgment through the real Next.js proxy. It saves a private receipt, so reruns use the second command instead of creating more records:

```powershell
docker compose exec -T backend python -m app.verify_phase3
docker compose exec -T backend python -m app.verify_phase3 --verify-existing
```

Both flows log out before returning. These are genuine public-source verification copies, not fabricated private case evidence. No datasets or model weights are downloaded again. Phase 3 must be reviewed before any commit/push or Phase 4 work.
