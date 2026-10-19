# Phase 3 review report — 2026-10-20

Phase 3 implements registration/login/logout/refresh, four roles, case ownership and sharing, case create/read/edit/search/archive, validated private evidence uploads/downloads, provenance/hash metadata and audit events. It extends the existing repository and data. The owner manually reviewed the working flow and authorized committing/pushing after final verification. Phase 4 is not started.

## Files and migration

New backend modules: `auth.py` (scrypt, JWT, cookies, CSRF, sessions, throttling), `case_api.py` (case authorization and workflows), `security_middleware.py` (actual body limits and no-store), `manage_users.py` (operator bootstrap), `verify_phase3.py` (real HTTP flow). Added `requirements-phase3.lock` and `tests/test_phase3.py`. Existing models, configuration, main routes, storage, operator CLI/import, Dockerfile and regression assertions were extended.

Additive `0003_private_workspace` follows Phase 2. It creates `users`, `auth_sessions` and `case_members`, adds case owner/dates/archive time and evidence uploader/capture date, and adds a separate schema marker. Restrictive foreign keys and legacy nullable ownership preserve all earlier rows without inventing identities. No tables/rows/volumes are dropped, no schema reset runs, and destructive downgrade is disabled. The operator evidence command now requires a real active uploader and checks that user's case access/role.

Frontend routes: `/register`, `/login`, `/cases`, `/cases/new`, `/cases/{id}`. Shared workspace components use actual responses, loading/error/empty states, pagination, sharing, case edits/archive, uploads, downloads and owner audit views. The streaming `/api/backend/[...path]` Next.js proxy forwards cookie/CSRF authentication to the fixed backend. The existing dashboard/health flow is retained and links into the workspace. Configuration, README, schema/architecture/implementation documents, smoke checks and API documentation were updated. See [API.md](API.md) for the full endpoint table and [SECURITY.md](SECURITY.md) for the precise role/access policy.

## Authentication and authorization

Public registration always assigns legal researcher; privileged roles cannot be self-assigned. All users manage their own cases; assigned researchers read/download, assigned investigators/lawyers also edit/upload; administrators access all cases with audited reads/downloads. Only owner/admin manages membership, archive and case audit history. Role changes revoke target sessions; the first administrator must be explicitly bootstrapped by the operator, and none is auto-created.

JWT cookies are HttpOnly and SameSite=Strict; no JWT enters browser storage or JSON. Access defaults to 15 minutes, refresh sessions to seven absolute days. PostgreSQL session revocation protects even unexpired access tokens. Refresh JWT hashes rotate and CSRF tokens are session-bound. Origin checks and double-submit CSRF cover mutations. Password hashing uses salted scrypt with N=131072; login failures lock accounts after five attempts and local request throttles bound repeated authentication attempts. Validation errors omit submitted secrets. Private responses disable caching; Uvicorn access logging is disabled to avoid private query metadata.

## Evidence and genuine working flow

PDF/PNG/JPG/JPEG/MP4 uploads enforce filename, signature/format, actual byte size and bounded parsing/decoding. MP4 validation uses FFprobe and FFmpeg with local protocols, disabled external data references, duration/resolution/codec constraints and timeouts. This is upload validation, not Phase 4/5 evidence analysis. Originals remain unchanged and content-addressed; metadata includes server timestamps, uploader, provenance, optional capture date and SHA-256. Duplicate originals within a case return 409. Authorized attachment downloads reverify the stored hash, record an audit event and return no private filesystem paths.

The opt-in real HTTP flow used the actual Next.js proxy to register, log in, refresh, create owner-authorized verification metadata, upload an unchanged copy of an existing licensed Supreme Court judgment, confirm persisted metadata/hash, retrieve the authorized original and log out. This is explicitly labeled public-source integration verification, not fabricated private case evidence. The source original was reused; no corpus/model download occurred.

- Verification case ID: `0210241e-0f95-4dad-86ec-d11f96c57efb`.
- Original evidence ID: `55cb1d58-6480-4a5e-8f91-d6a660b05642`.
- Unchanged PDF SHA-256: `120be20f98d20d1b3d8e0280f103e81c43965e3d99fa6827d5915835f66e7dc5`.

An isolated headless Microsoft Edge session also exercised the actual login and case pages, uploaded a PNG rasterization of the real source's first page, verified browser SHA-256 comparisons on upload/download, and logged out. Registration form rendering was checked; registration itself was exercised through the real HTTP flow and PostgreSQL tests. Browser automation reported zero runtime exceptions. The account/password, receipt, source-derived PNG, browser profile and downloaded files remain only under ignored `.local` storage. The account is a normal legal researcher, not an administrator.

## Verification results

Final full suite: **51 passed, 0 failed, 0 skipped**, in **122.52 seconds**, with two non-failing upstream deprecation warnings. This includes all 29 earlier regression cases (with the expected protected-route/new-head assertions updated) and 22 Phase 3 cases. The earlier 47-test and 50-test runs also passed before the final operator-import regression was added.

PostgreSQL was gracefully restarted and the final backend image recreated without resetting any volume. The existing verification account, case, PDF metadata, original SHA-256 and audit events were retrieved again through the Next.js proxy, followed by successful logout. Final corpus counts remained 3 sources, 50 judgments, 3,834 SQL passages and 3,834 Chroma vectors; statutes remained empty. The live verification case retains two genuine public-source originals (the PDF and its explicitly declared PNG page derivative). Alembic is at `0003_private_workspace (head)` with no schema drift; pip reports no broken requirements. All three long-running Compose services are healthy; migration exits successfully.

The tests use real PostgreSQL transactions/savepoints that are rolled back, plus genuine licensed corpus bytes and explicitly labeled derivatives for valid media. Invalid byte sequences are negative format tests, not fake evidence records. Tests cover invalid registration/login, role-injection rejection, scrypt verification, cookie flags, CSRF/origin rejection, expired/tampered/wrong-purpose/wrong-issuer/wrong-algorithm JWTs, refresh rotation/replay, logout revocation, case CRUD/search/archive, cross-user case/evidence access, assigned roles/revocation, administrator boundaries, all five supported extensions, duplicate detection, actual streamed size limits, traversal, integrity failure, scoped evidence IDs, download headers, audit records and preservation of Phase 1/2 features.

Linux frontend production build/TypeScript, native Windows TypeScript, headless Edge and real HTTP smoke checks (including 8 dashboard assets) passed. The two existing warnings concern Starlette's deprecated httpx TestClient adapter and Sentence Transformers' renamed embedding-dimension method. No retrieval-quality metric or legal accuracy claim is made.

The custom offline secret scan of all 70 Git-eligible text files passed, including common key/token patterns and exact matching against the actual local database password, generated JWT signing key and verification-account password. All 32 ignore probes passed, with additional checks confirming the actual private auth, evidence, Chroma/model and browser-download paths are ignored. No private binaries are tracked. This is a custom scan, not Gitleaks/TruffleHog. Git remains on `main` at Phase 2 commit `4800ceaa3b0d4214394b5b539b97259daf4ef691`, synchronized with its existing `origin/main`; all Phase 3 source/documentation changes are unstaged. No commit/push occurred.

## Exact startup and verification commands

From the repository root in PowerShell, retain the existing `.env`, PostgreSQL volume and private runtime directory:

```powershell
docker compose build backend frontend
docker compose up --no-build --wait --wait-timeout 180
docker compose ps --all
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
docker compose exec -T backend python -m pip check
docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_CORPUS_TESTS=1 backend python -m pytest -q -p no:cacheprovider
backend/.venv/Scripts/python.exe scripts/smoke.py
docker compose exec -T backend python -m app.verify_phase3 --verify-existing
```

Open http://localhost:3000/register or http://localhost:3000/login, with API docs at http://localhost:8000/docs. `verify_phase3` without `--verify-existing` is only for the first opt-in flow; it refuses to replace an existing private receipt. The existing local build workaround, if Docker compressed image export stalls, is:

```powershell
docker buildx build --output 'type=image,name=legal-evidence-backend,compression=uncompressed,push=false,store=true' ./backend
docker compose build frontend
docker compose up --no-build --wait --wait-timeout 180
```

Stop with `docker compose stop`; preserve the volume and private directory. Do not run destructive resets or repeat dataset/model acquisition. Native development additionally installs `backend/requirements-phase3.lock` and requires FFmpeg/FFprobe on PATH for MP4 validation.

## Remaining limitations and review gate

The instance remains loopback HTTP; `COOKIE_SECURE=false` is for that local setup only. HTTPS/secure cookies, email verification, password recovery/change, MFA, shared throttling, per-user storage quotas, antivirus/CDR and external tamper-resistant audit storage require a separate reviewed deployment/security scope. Current throttling is per-process for the single-worker deployment. Format validation does not certify evidence authenticity or malware absence. File and SQL commits cannot form one transaction; failed SQL writes can leave private unreferenced immutable blobs, which are retained for operator review instead of automatically deleted.

Phase 2 statute-source and representativeness limitations remain unchanged. No new legal material, private allegations, datasets, model weights or analysis outputs were invented or acquired. Private uploads and all credentials/runtime state remain excluded from Git. The owner approved the Phase 3 commit/push after manual review and final checks. Approved message: `feat: add authenticated case management and secure evidence uploads`. Phase 4 remains unauthorized.

## Approved pre-commit verification

The complete 51-test suite passed again in 172.17 seconds, with zero failures/skips and the same two non-failing warnings. Alembic found no schema drift and pip found no broken requirements. PostgreSQL retained 2 users, 2 cases and 3 evidence records from the genuine working flows and owner review, alongside all 50 judgments, 3,834 passages and 3,834 Chroma embeddings. All 53 judgment/evidence originals passed SHA-256 verification. No application functionality or UI was changed during this final review.

The custom secret scan found no secrets in the Git-eligible files, including exact checks for the actual generated local secrets; all 32 ignore probes passed. Additional custom static checks parsed 25 Python files, verified authentication dependencies on all 15 private routes, and found no flagged dynamic execution, shell=True, disabled TLS verification, destructive Phase 3 migration operations or private/generated artifacts eligible for Git. This is a source review and custom scan, not a dependency-advisory scan or penetration test. Local debugging/browser scripts, scan helpers, logs, credentials and private runtime files are excluded. The documented reusable `app.verify_phase3` command remains project verification source, without embedded credentials or data.
