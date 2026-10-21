# AI Legal Evidence Analysis System

## Final local application (Phase 8)

The integrated frontend is **LEXISCOPE - Legal Investigation Intelligence**. All data, analysis, permissions and report controls use the existing FastAPI services. The redesigned sidebar, live dashboard and case workspace connect evidence, document/visual analysis, research and report review. [Phase 8 delivery report](docs/PHASE8_REPORT.md) records actual verification and limitations. Earlier phase sections below are historical implementation references.

For this configured installation, start Docker Desktop, preserve the existing `.env`, `.local/phase2` and PostgreSQL volume, then run:

```powershell
docker compose up --no-build --wait --wait-timeout 180
```

Open **http://localhost:3000**; API documentation is **http://localhost:8000/docs**. Existing model/data/image caches are reused. Do not use `down -v` or reset private storage. After changing frontend source, rebuild only the frontend with `docker compose build --pull=false frontend` and start it with `docker compose up --no-build --no-deps --wait frontend`.

1. Register or sign in. Registration creates an unprivileged legal researcher; no credentials are seeded in source.
2. Open **Cases > Create case**, enter your own case metadata, then use the case sections: **Overview**, **Evidence & AI analysis**, **Legal research**, **Reports & review**, **Access & audit**.
3. Upload authorized PDF/JPG/PNG/MP4 evidence with its actual provenance. Original SHA-256 is verified. Use **Analyze Evidence**, **Analyze Image/Video**, and **View Analysis/Results** for real background jobs and source-linked observations.
4. In **Access & audit**, the owner can assign already registered collaborators. Investigators/lawyers can work on assigned active cases; researchers assigned to another person's case have read-only access. Case research/report generation requires investigator, lawyer or administrator role; report approval/rejection additionally requires an authorized lawyer or administrator.
5. Select completed extraction spans in case research and inspect the retrieved judgment sources. Use global **Legal research** for public judgment search. **Verified statutory recommendations are currently unavailable.**
6. Generate a report, inspect/preview/download its PDF and source snapshot, and record attributed notes plus an authorized explicit approval/rejection. The PDF stays immutable; approval is external and bound to its hashes. Log out using the identity panel.

For a genuinely fresh installation, configure `.env` from `.env.example` with your own strong database secret, build the services and migrate normally. Existing models/data require their documented provenance/license/acquisition steps and any required download approval; `--no-build` assumes the images already exist. To establish your intended first administrator, register that identity and use the existing trusted local operator command `docker compose exec -T backend python -m app.manage_users YOUR_REGISTERED_EMAIL --bootstrap-administrator`; it refuses if an active administrator already exists. Public registration cannot grant privileged roles. Never print or commit passwords, tokens, evidence, reports or private storage.

This is a **local academic application**, not production deployment. Statutory imports remain zero; AI outputs require human review and do not establish guilt, intent or admissibility. MFA, account recovery, production TLS/secure cookies, external audit signing, malware scanning, backups/host ACL review and deployment hardening remain production requirements. No external AI service, paid infrastructure or public deployment is added in Phase 8.

Academic investigation and legal research decision support for India. Phases 1 and 2 provide the application stack, 50 licensed public judgments and 3,834 persisted embeddings. Phase 3 adds cookie JWT authentication, case ownership/sharing, role checks, private evidence upload/download and audit logs. Keep services on loopback. See [the access policy](docs/SECURITY.md) before using private evidence.

## Phase 6 local legal research

Open http://localhost:3000/research for public source search. Log in and open an authorized case for exact extracted-page span selection, background research status, source passages and attributed review annotations. Initiation/review requires investigator, lawyer or administrator role plus active-case write access; other authorized readers may inspect completed research. The workflow is deterministic and local, with no external LLM/API.

Official statute import is currently disabled: access/reuse rights and complete legal-version metadata are not verified. BNS/BNSS/BSA and legacy imported section counts remain zero; unavailable statutory results are explicit. Existing judgment retrieval works without invented law. See [Phase 6 design](docs/PHASE6_DESIGN.md) and [report](docs/PHASE6_REPORT.md).

For this already configured workspace, preserve `.env`, private files and PostgreSQL volumes:

```powershell
docker compose up --no-build --wait --wait-timeout 180
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_CORPUS_TESTS=1 backend python -m pytest -q -p no:cacheprovider
docker compose exec -T backend python -m app.verify_phase6 --preservation-only
docker compose exec -T backend python -m app.verify_phase6 --verify-existing
```

The existing-result check requires the prior explicit operator demonstration receipt; `--run-flow` is an opt-in trusted local operator command that creates a dedicated investigator verification account/membership, then uses genuine existing evidence and records real research/review results. It never changes an existing user's role or modifies original evidence. Credentials, private reports and runtime data stay ignored. The owner approved the Phase 6 commit/push subject to final verification. UI redesign and Phase 7 remain unauthorized.

## Requirements

Phase 5 adds local YOLOX/OpenCV image and sampled-MP4 object candidates to the existing evidence pages. Use **Analyze Image** / **Analyze Video** and **View Results** after logging into an authorized case. Results show private source/annotated frames, elapsed presentation timestamps, source hashes and actual model scores; they do not identify people or establish criminal activity. See [Phase 5 design and access policy](docs/PHASE5_DESIGN.md) and [verification report](docs/PHASE5_REPORT.md).

For this already configured workspace, preserve all existing private files and start the built services without downloads:

```powershell
docker compose up --no-build --wait --wait-timeout 180
docker compose exec -T backend alembic check
docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_CORPUS_TESTS=1 backend python -m pytest -q -p no:cacheprovider
docker compose exec -T backend python -m app.verify_phase5 --verify-existing
```

The last command requires the opt-in visual flow receipt; `python -m app.verify_phase5` runs that authorized genuine-media flow once. `--preservation-only` verifies all pre-Phase-5 row fingerprints and current original/artifact hashes. These verification commands never acquire models or datasets. New environments require explicitly approved acquisition using the pinned helpers and provenance documented in the report. Phase 5 was reviewed, committed and pushed as `37ed922`; Phase 6 is authorized as described above and stops for review.

Phase 4 adds asynchronous PDF/image OCR and source-linked NLP analysis to authorized evidence pages. It reuses the installed OCR/CPU stack and the explicitly approved local NER snapshot. Details: [design, API, schema and model register](docs/PHASE4_DESIGN.md), [verification results and limitations](docs/PHASE4_REPORT.md). Preserve the existing `.env`, PostgreSQL volume and `.local/phase2`.

```powershell
docker compose build backend frontend
docker compose up --no-build --wait --wait-timeout 180
docker compose exec -T backend alembic check
docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_CORPUS_TESTS=1 backend python -m pytest -q -p no:cacheprovider
```

Login, open an authorized case, select **Analyze Evidence**, then **View Analysis** after completion. The separate `worker` service supplies status/progress/retry; no upload or API request performs OCR/inference. Completed page text, candidate entities, exact offsets, hashes and genuine score provenance are displayed without a redesign. Unsupported video analysis remains Phase 5.

An opt-in real worker evaluation reuses the existing private Phase 3 verification receipt and licensed judgment, uploading declared page derivatives only on its first run:

```powershell
docker compose exec -T backend python -m app.verify_phase4
docker compose exec -T backend python -m app.verify_phase4 --verify-existing
```

Measurements and receipts remain private under `.local/phase2/auth`; the worker cannot mount that directory. The command compares with existing source text and reports its reference limitations. It does not fabricate ground-truth accuracy. Phase 4 requires owner review before any commit/push or Phase 5 work.

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

Both Phase 3 flows log out before returning. These are genuine public-source verification copies, not fabricated private case evidence. No datasets or Phase 2 weights are downloaded again. Phase 3 has been reviewed and pushed; Phase 4 is now explicitly authorized and must stop for its own review before any commit/push or Phase 5 work.


## Phase 7 private investigation reports

Phase 7 is reviewed and approved for commit/push subject to final staged-content checks: **135 passed, 0 failed, 1 gated statute-data skip**. Phase 6 is pushed as `a917344`. The existing case page now queues deterministic private report generation, shows status/version history, previews/downloads hash-verified PDF and source snapshots, and records attributed notes plus explicit lawyer/administrator approval or rejection. Reports preserve source references, distinguish automated observations from human interpretations, and remain review copies with externally recorded approval. No guilt, admissibility or statutory recommendation is asserted; verified statutory imports remain zero. See [PHASE7_REPORT.md](docs/PHASE7_REPORT.md) for actual verification, API/role/limit details and exact commands. The owner approved Phase 7 commit/push after exact-file review and a final staged-content scan. UI redesign and Phase 8 remain unauthorized.

```powershell
docker compose up --no-build --wait --wait-timeout 180
docker compose exec -T backend python -m app.verify_phase7 --preservation-only
docker compose exec -T backend python -m app.verify_phase7 --verify-existing
```
