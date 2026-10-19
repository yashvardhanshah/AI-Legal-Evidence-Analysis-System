# Phase 1 verification

Execution date: 2026-10-19. Results are recorded after execution below.

## Reproduce

```powershell
Set-Location backend
.venv/Scripts/python.exe -m pytest -q
$env:RUN_DB_TESTS='1'
.venv/Scripts/python.exe -m pytest -q
Remove-Item Env:RUN_DB_TESTS
.venv/Scripts/alembic.exe current
.venv/Scripts/alembic.exe check
Set-Location ../frontend
npm run typecheck
npm run build
Set-Location ..
docker compose config --quiet
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://localhost:8000/api/v1/health/ready
Invoke-RestMethod http://localhost:3000/api/system
git diff --check
git status --short --branch
```

Backend tests cover liveness, sanitized database failures, CORS origin restrictions and absence of unimplemented domain routes. The opt-in PostgreSQL integration test checks readiness and commits a non-sensitive metadata probe, reads it through a separate connection, and deletes that probe. It does not substitute SQLite or a mocked database for persistence verification.

Manual browser review should check mobile navigation, keyboard focus, unavailable and loading states, refresh, readable contrast and disabled future modules. No visual browser verification is claimed unless explicitly recorded.

## Executed results

| Check | Observed outcome |
| --- | --- |
| Tools | Git 2.49.0; Node 22.14.0; npm 10.9.2; Python 3.13.5; Docker engine 29.5.3; Compose 5.1.4; native PostgreSQL 18 tools |
| Repository | Empty local main; correct origin; remote HEAD and branch refs empty at initial and final read; no commit, stage or push performed |
| Backend unit checks | 4 passed, PostgreSQL check skipped when not explicitly enabled |
| Backend with RUN_DB_TESTS=1 | 5 passed against real isolated PostgreSQL; committed probe read across connections and removed |
| Alembic | upgrade head succeeded; current=0001_foundation; check reported no new upgrade operations |
| Python dependency integrity | pip check: no broken requirements |
| Frontend | Production build and TypeScript check passed on Windows; production build also passed inside Linux Docker image |
| npm advisories | Install audit: zero vulnerabilities; final production dependency audit: zero vulnerabilities at check time |
| HTTP integration | scripts/smoke.py passed: liveness, actual database readiness, frontend proxy, rendered HTML and 8 built CSS/JS assets |
| Actual backend outage | Stopped FastAPI; Next.js proxy returned expected sanitized HTTP 503 body |
| Docker | All application images built; full compose up --build --wait succeeded; db, backend and frontend healthy; migrate exited 0 |
| Containerized backend suite | 5 passed; real PostgreSQL persistence; Alembic found no schema drift; pip check passed |
| Containerized HTTP integration | scripts/smoke.py passed for API, actual DB readiness, frontend proxy, HTML and all 8 referenced assets |
| Git hygiene | Generated password absent from all 39 Git-eligible files at scan; env, evidence, dataset, model and DB paths ignored; .env.example eligible; diff check passed |

An initial database integration run failed because test setup overrode the configured database URL with the intentionally unreachable unit-test URL. The override now applies only to unit mode; the rerun passed. Initial sandbox restrictions blocked package networking and Node path resolution; approved retries completed successfully.

Known non-failing warning: Starlette's TestClient deprecates its current httpx adapter in favor of httpx2. Tests pass with the locked adapter; a future dependency update should migrate it. A cross-account pytest cache permission warning was avoided in the final integration run with `-p no:cacheprovider`.

No browser automation tool was available; browser rendering, keyboard behavior, hydration and mobile layout were not visually verified. HTTP asset checks are not a substitute for browser QA. No AI, authentication, case CRUD, evidence ingestion or end-to-end legal workflow is claimed in this phase.

The native verification cluster is preserved in ignored `.local/pgdata`; native test servers and that cluster were stopped after verification. The existing system PostgreSQL service and its data were not changed. Reproduction commands for the native fallback are in README.md.

Normal Docker pulls repeatedly failed at Docker Hub with connection EOF errors. BuildKit successfully fetched the standard official PostgreSQL 18 image using `'FROM postgres:18' | docker build --tag postgres:18 -`. This resolved the blocker; the complete Compose stack subsequently passed startup and integration tests. No third-party mirror was used.

The requested Docker application remains running for local review at http://localhost:3000, with API docs at http://localhost:8000/docs. Ports are bound to loopback only. Run `docker compose stop` to stop services while keeping containers and data, or `docker compose down` to remove containers while preserving the named database volume. No unresolved Phase 1 runtime failure remains; browser QA and the non-failing test-adapter deprecation warning remain documented limitations.

## Pre-commit security review

Following the owner's Phase 1 review, an offline pattern-based secret scan of all 39 Git-eligible files found no secrets. Checks covered private keys, common provider tokens, JWTs, credential URLs, literal credential assignments and the actual generated local database password. Intentionally inert test credentials and the sanitized `.env.example` placeholder were reviewed as exceptions. All 32 ignore-rule probes passed for credentials, environment files, evidence uploads, datasets, local databases, models and generated files. Generic upload, credential, download and cache exclusions were strengthened. This was a local custom scan; Gitleaks and TruffleHog were not installed. Exact staged blobs are rescanned before the commit.
