# AI Legal Evidence Analysis System

Academic investigation and legal research decision support for India. Phase 1 provides a Next.js interface, FastAPI API, PostgreSQL foundation migration and local Docker Compose stack. Authentication, cases, evidence, AI analysis and legal retrieval are **not implemented yet**. Do not load private evidence or expose these services publicly.

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
Set-Location backend
.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
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

If normal pulls fail with Docker Hub connection EOF errors, the standard image was successfully fetched through BuildKit with this command before retrying Compose:

```powershell
'FROM postgres:18' | docker build --tag postgres:18 -
```

## Version control

Origin: https://github.com/yashvardhanshah/AI-Legal-Evidence-Analysis-System.git, branch `main`. GitHub had no refs at the initial read on 2026-10-19. Phase 1 has been reviewed by the project owner. Every commit and push requires explicit user approval; recheck remote refs before pushing. `.gitignore` is a safeguard, not a replacement for reviewing every staged file. Keep original evidence, datasets, models, credentials and database backups outside Git.

Implementation references: [Next.js installation](https://nextjs.org/docs/app/getting-started/installation), [FastAPI containers](https://fastapi.tiangolo.com/deployment/docker/), [Compose service dependencies](https://docs.docker.com/compose/how-tos/startup-order/).
