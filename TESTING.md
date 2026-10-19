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


## Phase 2 final verification — 2026-10-19

Final Docker suite: **29 passed, 0 failed, 0 skipped**. Run with:

```powershell
docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_CORPUS_TESTS=1 backend python -m pytest -q -p no:cacheprovider
docker compose exec -T backend alembic check
docker compose exec -T backend python -m pip check
backend/.venv/Scripts/python.exe scripts/smoke.py
```

Actual corpus: 50 unique real Supreme Court judgments, 1,274 pages, 3,834 passages and 3,834 persisted embeddings. Initial ingestion had no failed or duplicate documents. Reindexing added zero vectors; the existing count stayed 3,834. A clean PostgreSQL restart preserved the corpus and Phase 1 marker. A separate Python process reopened Chroma and confirmed the persisted count. SQL joins verified actual source excerpts and source URLs, with distinct judgments returned in final semantic search.

All corpus documents used real embedded PDF text. Actual Tesseract 5.5.0 fallback was additionally tested using a rasterized derivative of a genuinely acquired source page. Migration tests use an isolated schema in a rolled-back transaction; failure/retry tests likewise roll back their job fixtures. No synthetic legal records or private evidence are seeded. Core checks initially passed 22 tests with 7 corpus checks waiting for data/model availability; all 29 passed once genuine ingestion/indexing completed.

Windows storage testing first found read-only temporary hard links could not be removed. The implementation now removes the temporary link before marking the preserved original read-only; reruns pass. The initial live search returned overlapping chunks from one case; final retrieval groups the best passage per judgment and a regression assertion verifies distinct IDs. No source text or vector values were fabricated to change those results.

Windows and Linux frontend builds/TypeScript, full Docker health, Alembic no-drift, pip consistency and real HTTP checks (including all 8 frontend assets) passed. The layout is unchanged; only a stale no-datasets claim was corrected. Two non-failing warnings remain: Starlette's httpx TestClient adapter and Sentence Transformers' legacy dimension-method name. No visual browser QA or labeled retrieval-quality evaluation was performed.

All originals/model/cache/vector files stay under ignored private runtime storage. A working-tree scan of all Git-eligible files checked common key/token/private-key patterns, credential URLs, literal credentials and the actual local database password; no unreviewed secrets were found. All 32 ignore probes passed. One deliberately invalid credential URL in a URL-rejection unit test is explicitly reviewed as a test fixture, never used for network access. No dedicated Gitleaks/TruffleHog scan is claimed.

See [the Phase 2 report](docs/PHASE2_REPORT.md) for measured search results, exact source links, files changed, storage sizes, limitations and startup commands. India Code statutory text remains unimported pending access/rights review; its endpoint correctly returns an empty collection. Case/evidence tables remain empty and inaccessible over HTTP until Phase 3 authorization exists.

## Approved Phase 2 pre-commit verification — 2026-10-20

The full Docker suite passed again: **29 passed, 0 failed, 0 skipped**, with the same two non-failing deprecation warnings (137.94 seconds). Alembic reported no new upgrade operations and pip reported no broken requirements. Windows frontend TypeScript and production build passed; real HTTP smoke checks passed for liveness, database readiness, frontend proxy, dashboard HTML and all 8 built assets.

Reviewed all 31 staged source/configuration/test/documentation paths. The exact staged-blob custom secret scan found no secrets; all 32 ignore probes passed. PDFs, downloaded datasets, Chroma data, model weights, private environment files and local runtime artifacts are excluded. The sanitized `.env.example` remains intentionally tracked. Branch `main` and the expected GitHub origin were verified, with remote `main` matching the Phase 1 base before the approved commit. Phase 3 remains unauthorized.

## Phase 3 final verification — 2026-10-20

Phase 3 was subsequently authorized. The final complete Docker run passed **51 tests, 0 failed, 0 skipped**, with **2 non-failing upstream deprecation warnings**, in **122.52 seconds**:

```powershell
docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_CORPUS_TESTS=1 backend python -m pytest -q -p no:cacheprovider
```

All 29 earlier regression cases remain, with the intentional expectations updated from nonexistent case routes to authenticated 401 responses, and from the Phase 2 migration head to Phase 3. Database-foundation checks permit genuine user-owned cases while checking for unexpected ownerless/uploaderless records. The 22 Phase 3 cases cover registration, role injection, salted scrypt, invalid login/lockout, CSRF/origin, cookie flags, JWT expiry/signature/purpose/issuer/algorithm, refresh rotation/replay, logout, case CRUD/search/archive, cross-user access, memberships and all assigned roles, administrator changes/session revocation, scoped evidence IDs, all five supported extensions, actual streamed size enforcement, filenames, corruption detection, download headers/audits and the retained operator-import authorization boundary.

Integration fixtures use real PostgreSQL savepoints and roll back their account/case/evidence/audit writes. Valid files use the already acquired licensed Supreme Court PDF and declared PNG/JPEG/MP4 derivatives of its real first page; invalid byte sequences are rejection fixtures, not fabricated live evidence. No new corpus/model download or database reset occurred.

The live Next.js-proxy flow successfully registered, logged in, refreshed, created user-authorized verification metadata, uploaded an unchanged real source judgment, saved metadata, compared SHA-256, downloaded the authorized original and logged out. An isolated headless Edge session rendered registration, logged in, displayed the actual case, uploaded a genuine source-page PNG, verified browser-side upload/download hashes and logged out with zero runtime exceptions. These live records are explicitly labeled public-source verification, not private legal allegations. Secrets, receipts, derivatives and the isolated browser profile/downloads remain ignored under `.local`.

PostgreSQL was gracefully restarted and the backend recreated. The same account, case, evidence metadata, original hash and audit events were then verified through real HTTP, followed by logout. Corpus counts remained **50 judgments, 3,834 passages and 3,834 Chroma vectors**; the actual persistence test reopened the index in a separate process. Final live evidence count is two, both authorized public-source verification files. The Phase 1 installation and Phase 2 schema markers remain intact. Alembic reports `0003_private_workspace (head)` and no new upgrade operations; pip reports no broken requirements. Compose backend/frontend/database are healthy and migration exits 0.

Linux production frontend build/TypeScript, Windows TypeScript and real HTTP smoke checks all passed, including liveness, PostgreSQL readiness, Next.js proxy, dashboard HTML and eight built assets. The existing Starlette httpx adapter and Sentence Transformers dimension-method deprecation warnings remain non-failing. Browser behavior was checked with headless Edge; broader cross-browser/device QA is not claimed.

The final custom pattern scan covers all 70 Git-eligible files and the actual database password, JWT key and verification-account password; no findings. All 32 ignore probes passed; actual auth/evidence/Chroma/model/browser paths are ignored, and no private binary artifact is tracked. No Gitleaks/TruffleHog scan is claimed. No Phase 3 files are staged, committed or pushed. See [PHASE3_REPORT.md](docs/PHASE3_REPORT.md), [API.md](docs/API.md) and [SECURITY.md](docs/SECURITY.md) for startup commands, the complete endpoint/role policy, changed files and remaining local-deployment limitations. Stop for owner review before committing/pushing or beginning Phase 4.

## Approved Phase 3 pre-commit verification — 2026-10-20

After the owner's successful manual review and explicit commit/push approval, the full suite passed again: **51 passed, 0 failed, 0 skipped**, with the same **2 non-failing warnings**, in **172.17 seconds**. Alembic reported no new upgrade operations and pip reported no broken requirements. Real HTTP smoke checks passed for liveness, readiness, the frontend proxy, dashboard HTML and all eight built assets.

Read-only checks confirmed 2 users, 2 cases and 3 evidence records remain in PostgreSQL, with all 50 judgments, 3,834 passages, 3,834 Chroma embeddings and all three installation/schema markers intact. Every one of the 53 judgment/evidence original files passed its recorded SHA-256 check. Tests rolled back their fixtures; no database resets, new ingestion or UI/functionality edits occurred during this review.

The source secret scan found no secrets, including the actual local database password, JWT key and verification-account password; all 32 ignore probes passed. Custom static checks parsed 25 Python files and confirmed explicit authentication dependencies on all 15 private routes, with no flagged dynamic code execution, shell execution, disabled TLS verification, destructive Phase 3 migration operations or private/generated Git-eligible artifacts. These checks do not claim a dependency vulnerability database or penetration test. Only the 38 approved source, configuration, migration, test and documentation paths are selected for staging; `.local` debugging/browser scripts, logs and all private runtime artifacts remain excluded. Exact staged blobs are rescanned before committing. The branch and expected origin were verified against the Phase 2 remote base. Phase 4 remains unauthorized.
