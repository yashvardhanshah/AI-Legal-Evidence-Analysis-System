# Phase 7 verification report

Phase 7 implements deterministic investigation report generation, immutable provenance snapshots, private PDF export and attributed review/approval. The owner reviewed Phase 7 and approved commit/push subject to exact-file review and a final staged-content secret scan. UI redesign and Phase 8 remain unauthorized.

## Architecture and source boundaries

See [PHASE7_DESIGN.md](PHASE7_DESIGN.md) for the architecture, exact permissions, snapshot selection, integrity checks, resource bounds and limitations. New source modules are `report_sources.py`, `report_pdf.py`, `report_jobs.py`, `report_api.py` and the opt-in operator verifier `verify_phase7.py`. The existing worker, router, models, case page and Compose are extended. New `reports.tsx` reuses the current frontend/API architecture for generation/status/history, hash-verified PDF preview/download, snapshot/provenance/audit, annotations and approval/rejection. No external AI service is configured or called; no evidence content is sent outside the local services.

The source selection is explicit: all case evidence, latest completed document/vision analysis per evidence and all completed case research runs and their existing relevance notes at capture time. Summaries count/attribute actual retained records, without inferring allegations or conclusions. Genuine data controls section inclusion. Original evidence remains immutable. Report snapshots include actual analysis/model IDs, source hashes, Unicode offsets, frame indices/timestamps, detected bounding boxes/confidence, saved judgment excerpts/metadata/source URLs and publisher/license attribution.

**Verified statutory analysis remains unavailable. Imported provisions: BNS 0; BNSS 0; BSA 0; legacy IPC/CrPC/Indian Evidence Act 0.** Reports, APIs and UI do not offer unsupported statutory recommendations or establish guilt, liability or admissibility. The authentic-statute parsing/effective-date test remains skipped because official source rights and legal-version metadata are unverified. Phase 4's observed 1 of 6 checked person mentions is disclosed as a sample limitation, not general NLP accuracy.

## Database, background jobs and review

Additive migration `0007_case_reports` adds two tables, restrictive references and immutable/append-only triggers. No pre-existing table/record/volume is reset. During development, before any live report versions existed, the new table's completed-output check and review trigger were tightened to match the final migration; no old data was edited. Isolated migration regressions apply the complete chain twice inside a rollback schema.

Report jobs use persisted PostgreSQL status/progress, three-attempt bounded retry, stale-worker fencing, subprocess deadlines and an isolated `report-worker`. Each attempt retains its own case version; only a valid current lease and current case permissions can publish a completed PDF. Completed versions cannot be updated/deleted through the database guards or API. Notes and explicit decisions retain author name/ID/role, timestamp, disposition, PDF hash and snapshot hash. Generation/notes require authorized investigator/lawyer/administrator access; approval/rejection additionally requires lawyer or administrator. No independent second-person/self-approval separation policy is claimed. Terminal decisions are immutable and revisions require another version.

The immutable PDF is a review copy, with later approval recorded externally and hash bound. It never silently changes after inspection or claims its own final hash internally. API metadata supplies actual review status and approval state; unapproved PDFs are explicitly not finalized investigations. Human approval is an attributed decision, not a factual/legal certification. Post-generation report annotations remain external; source Phase 6 relevance annotations captured at generation are included in the human interpretation section.

## APIs

All endpoints below are authenticated and scoped under `/api/v1/cases/{case_id}`; each checks the current user/case relationship and mutating requests retain CSRF/origin enforcement.

| Method/path | Purpose |
| --- | --- |
| POST /report-jobs | Start/reuse background generation; `new_version:true` captures a fresh completed-version successor |
| GET /report-jobs | Paginated scoped job history |
| GET /report-jobs/{job_id} | Actual status/progress, sanitized failure and retained attempt versions |
| POST /report-jobs/{job_id}/retry | Bounded retry, current authorization and duplicate/capacity checks |
| GET /reports | Paginated immutable version history with review states |
| GET /reports/{report_id} | Version metadata, external hashes and attributed reviews |
| GET /reports/{report_id}/pdf | Verified attachment, or `?preview=true` review-copy PDF |
| GET /reports/{report_id}/snapshot | Verified exact canonical JSON source snapshot attachment |
| GET /reports/{report_id}/provenance | Snapshot and current external review metadata |
| GET /reports/{report_id}/audit | Paginated report/job-scoped audit history |
| POST /reports/{report_id}/reviews | Append a note or terminal explicit approved/rejected decision bound to inspected hashes |

## Dependency provenance and PDF format

Pinned [ReportLab 5.0.1](https://pypi.org/project/reportlab/5.0.1/) is BSD licensed. The PyPI universal wheel was downloaded once: **1,957,258 bytes**, SHA-256 `1c36e6bb0e71780c72331eba60da7f602e8d4389a8723825af71342e49d791e8`. The actual publisher digest was checked before an offline `--no-index --no-deps` installation into the retained Phase 6 image. Existing Pillow 12.3.0 and charset-normalizer 3.5.2 satisfy dependencies; pip check passed. No new model, judgment dataset or test-media acquisition was needed. Frontend production compilation uses the unchanged lockfile; actual build outcomes are recorded below.

The A4 PDF has a cover, confidentiality/review-copy notices, unique ID/version/case reference/capture timestamp, deterministic executive summary, recorded case information/participants, optional source-dependent inventory/document/vision/research/human-note sections, limitations and an integrity/model/source-license appendix. Page-number footers identify the report/version. Long source text wraps and flows across pages; untrusted text is escaped before PDF markup. No source URL is fetched by the renderer. Exact Unicode remains in the JSON; unsupported font glyphs are shown as `[U+XXXX]`, and complex-script shaping is unsupported. PDF/A, cryptographic signatures and universal multilingual layout are not claimed.

## Verification record

The first focused run stopped at **0 passed, 1 failed, 0 skipped**, one upstream warning, **15.79 seconds**: test isolation pointed retained judgment citation checks at the temporary output root. The test's verified source-store overlay was corrected; citation integrity errors now fail explicitly as `integrity_failed`, without production exception details. A diagnostic rerun used an ignored local harness/log; it is not project source. The next focused run passed **18 tests, 0 failed, 0 skipped**, one existing upstream warning, **115.84 seconds**. Further stale-worker, tamper and cap tests were added afterward; final results are recorded below.

Windows TypeScript passed after an initial sandbox parent-directory `EPERM` required a normal local-access rerun. No dependency or code change was needed to resolve that environment restriction. Final complete regressions, real worker/browser flow, persistence and security results are recorded below from actual execution.

## Startup and verification commands

Preserve `.env`, `.local/phase2` and the named PostgreSQL volume. Start already built images without acquisition:

```powershell
docker compose up --no-build --wait --wait-timeout 180
docker compose ps --all
docker compose exec -T backend alembic current
docker compose exec -T backend python -m pip check
docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_CORPUS_TESTS=1 backend python -m pytest -q -p no:cacheprovider
docker compose exec -T backend python -m app.verify_phase7 --preservation-only
docker compose exec -T backend python -m app.verify_phase7 --verify-existing
```

The local incremental build reuses installed dependencies and the verified ReportLab wheel:

```powershell
docker build --pull=false -t legal-evidence-backend:phase7-deps .local/phase7
docker buildx build --pull=false --file .local/phase7.Dockerfile --output 'type=image,name=legal-evidence-backend,compression=uncompressed,push=false,store=true' ./backend
docker compose run --rm --no-deps migrate
docker compose up -d --no-build --no-deps backend worker visual-worker research-worker report-worker
docker compose build --pull=false frontend
docker compose up -d --no-build --no-deps frontend
```

Those `.local` helpers/images are local acquisition optimizations, not committed dependencies. Fresh environments use `backend/Dockerfile` and `requirements-phase7.lock`, with their own acquisition budget. An explicit trusted operator may run `docker compose exec -T backend python -m app.verify_phase7 --run-flow` once: it reuses the Phase 6 investigator, registers a new dedicated reserved-domain reviewer and locally grants only that new identity lawyer role/case membership, then runs real HTTP generation/review/approval/rejection/download/logout. It does not edit old roles, cases or evidence. Credentials, PDFs and private receipts remain ignored. Subsequent `--verify-existing` does not generate/requeue reports or create identities. Stop services with `docker compose stop`; never remove volumes/originals.


## Real report generation, browser and persistence results

The actual case-scoped source snapshot contains **6 evidence records, 3 latest completed document analyses, 2 visual analyses, 2 completed research runs and 2 captured human relevance annotations**. This is one authorized case; the global 7 evidence records across both cases remain intact. Earlier document-analysis versions remain preserved but are not duplicated into the report as current analyses.

The real background worker generated **three immutable 40-page PDFs**. Versions 1 and 2 were generated through the opt-in operator/HTTP flow; version 3 was generated through the installed Edge UI. Each completed on its first attempt. Version 1 is **115,874 bytes**, version 2 **115,871 bytes** and version 3 **115,893 bytes**. Observed creation-to-finish wall times for the first two versions were **6.365493 seconds** and **2.230926 seconds** respectively, excluding queue wait; these are individual local observations, not throughput or accuracy benchmarks. Both final PDF and canonical JSON snapshot SHA-256 values were independently checked against actual downloaded bytes, and all inventory hashes were present in extracted PDF text.

Version 1 was explicitly approved and version 2 explicitly rejected by the newly registered dedicated local verification lawyer. The investigator's preceding notes and lawyer decisions are attributed separately. The initial verifier completed both generation jobs but received a **403** when switching identities after logout because it had not obtained a fresh CSRF cookie. Only the verifier was corrected to reinitialize CSRF; the application protection was preserved. An immediate post-recreation retry then returned a transient **503** before backend health recovered. After explicitly waiting for healthy services, the saved two reports were inspected/reviewed successfully without regenerating them or creating duplicate identities. These intermediate failures are retained rather than reported as successful flows.

Installed headless Edge subsequently passed investigator login, Generate Report/new-version request, actual background completion/history, hash-verified Preview PDF and Download PDF, provenance inspection, investigator annotation, lawyer login/approval and logout with **0 runtime exceptions**. This created version 3, which is approved; its PDF hash stayed unchanged after approval. Across all three versions there are **6 append-only review records** (one investigator note and one terminal lawyer decision per version). Final terminal states are **2 approved, 1 rejected**. PDF hashes/metadata do not imply that human review establishes truth or legal admissibility. Local rendered cover and source-text pages were visually inspected and were readable, with margins/footer and clear review-copy/source labels; no all-language or all-viewer rendering claim is made.

After graceful PostgreSQL/backend/document-worker/visual-worker/research-worker/report-worker/frontend restarts, all **3 report-version and 6 review row fingerprints**, canonical snapshot hashes and private PDF hashes matched their pre-restart checkpoint exactly. Existing-report HTTP download/review/provenance/audit checks passed without enqueueing or uploading. Every pre-Phase-7 domain-row and **308 existing audit-event fingerprints** remained unchanged, including both existing cases and the three original users; the one new dedicated lawyer/membership is an intentional verification addition. Preserved data include **50 judgments, 3,834 SQL passages/Chroma embeddings, all 57 original hashes, 20 earlier artifact hashes, 6 OCR/NLP runs/16 pages/428 entities, 2 vision runs/7 sampled frames/84 detections, 2 research runs/3 inputs/7 results/2 source reviews**. All embedding contents/IDs/metadata match the original aggregate checkpoint, beyond the count check. No data reset, evidence transformation, dataset/model re-download or old-role change occurred.

All **7 services** recovered healthy. Alembic is `0007_case_reports (head)` with **no new upgrade operations detected**. Pip reports **no broken requirements**. Existing HTTP smoke checks passed liveness, PostgreSQL readiness, frontend proxy, dashboard HTML and **8 built assets**. Production Next.js and Windows TypeScript passed. The frontend build refreshed Node base layers and installed **54 packages** from the unchanged lockfile; it was not fully cache-only. There was no new Node dependency selection, model/data acquisition or paid service call. The exact ReportLab wheel acquisition is recorded above.

## Additional focused verification

The expanded focused suite initially returned **19 passed, 1 failed, 0 skipped**, one existing warning, in **149.81 seconds**. Its new page-tamper test changed an older historical analysis that the explicit latest-completed selection policy excludes. The test was corrected to tamper with the latest included analysis; the policy and source checks were not weakened. The final focused suite passed **22 tests, 0 failed, 0 skipped**, one existing upstream warning, in **140.46 seconds**. Tests cover genuine PDF generation/text extraction/multi-page output, inventory and source references, actual judgment/citation correspondence, source spans, every private read route's anonymous/cross-case denial, read-only/unprivileged ownership, archival, duplicate/new version behavior, immutable database guards, CSRF/role/hash-bound approval and rejection, empty-case omission, current-access revocation, failed renderer recovery, stale-child fencing/restart claiming, source/citation/snapshot/PDF tampering, retry caps, audit/provenance and literal markup escaping. Controlled failure/tamper metadata is a rolled-back negative fixture and is not published as evidence or legal material.

The earlier ignored diagnostic rerun of the first storage-isolation failure returned **0 passed, 1 failed, 0 skipped**, two warnings, **4.67 seconds**; it was diagnostic, not a successful verification. All intermediate runs and final complete-suite results are recorded in TESTING.md. No timeout or assertion was relaxed to pass these checks.


## Full-suite verification and preserved-history isolation - 2026-10-22

The first complete Phase 1-7 run returned **114 passed, 21 failed, 1 skipped**, with **2 existing upstream warnings**, in **572.02 seconds (9 minutes 32 seconds)**. All 113 earlier passing regressions passed, plus the new empty-case report test; the authentic-statute-data test remained deliberately skipped. The other 21 new Phase 7 cases reused the already completed live demonstration job because their default title matched its case/title reuse key. They then incorrectly expected to claim a fresh queued job. This was test isolation against preserved history, not a failed real report generation or authorization bypass.

The enqueue helper now assigns a unique title from each fixture's newly registered user ID, while repeated calls within that fixture still exercise real duplicate reuse and explicit new-version behavior. No application code, reuse policy, case data, report, review, assertion, timeout or source integrity check was changed. The live reports and all prior histories remain preserved. The complete suite is rerun using the same database/corpus-enabled command, with no concurrent build or real queue processing; its actual final result follows below.


## Final Phase 7 verification - 2026-10-22

The corrected complete Phase 1-7 regression suite passed **135 tests, 0 failed, 1 skipped**, with **2 existing upstream warnings**, in **738.56 seconds (12 minutes 18 seconds)**:

```powershell
docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_CORPUS_TESTS=1 backend python -m pytest -q -p no:cacheprovider
```

This includes all **113 earlier passing tests** and **22 new Phase 7 cases**, run against the preserved real report history. The one skip remains authentic statutory parsing/effective-date verification because official rights/access/version metadata are unverified and **zero BNS, BNSS, BSA or legacy provisions** have been imported. The two warnings are the existing Starlette/httpx test adapter and Sentence Transformers dimension-method deprecations. The earlier full-suite failure and its fixture-isolation correction remain recorded above; no application behavior, data, timeout or source-integrity assertion was relaxed.

After this final full run, read-only verification again matched **every pre-Phase-7 domain/audit baseline row**, all **57 original and 20 earlier artifact hashes**, all **3,834 embedding contents/IDs/metadata**, and the **3 real report-version/6 review fingerprints**, PDF hashes and canonical snapshot hashes against their checkpoints. Counts remain **50 judgments, 3,834 passages/embeddings, 7 evidence records, 2 existing cases, 6 OCR/NLP runs/16 pages/428 entities, 2 vision runs/7 frames/84 detections and 2 research runs/3 inputs/7 results/2 source reviews**. Original users/roles and all 308 prior audit events remain intact; the dedicated new lawyer/membership and three report jobs are intentional additions. No original, database volume or analysis history was reset or replaced.

All **66 backend project files** matched the tested container byte-for-byte. Final custom privacy/secret checks reviewed **117 Git-eligible files** against common credential patterns and **5 actual local secret values**, with **0 findings**. All **46 ignore probes** passed: the earlier 42, two private report directories and both actual exported-snapshot filename patterns. Static checks parsed **56 Python files**, checked **50 authenticated private routes** and found no flagged destructive migration or private/generated eligible file. Git whitespace checks passed. The production frontend build's npm audit reported **0 vulnerabilities** at build time; no broader Python dependency-CVE audit or penetration-testing claim is made. Private reports/snapshots, original PDF/media/evidence, datasets/models, actual environment/credential files, databases/volumes, browser profiles, local wheels/helpers/logs and generated outputs remain excluded.

Final source scope is **28 paths: 17 modified, 11 new**, comprising source, tests, additive migration, dependency lock/configuration, ignore rules and documentation. New backend modules are `report_api.py`, `report_jobs.py`, `report_pdf.py`, `report_sources.py` and `verify_phase7.py`; new migration/test/lock are `0007_case_reports.py`, `test_phase7.py` and `requirements-phase7.lock`; new frontend is `workspace/reports.tsx`; new documents are this report/design reference. Existing worker dispatch, router/readiness, schema models, Dockerfile/Compose, minimal case-page integration, migration-head regression and architecture/source/security/startup/testing documents are updated.

Repository remains on **main** at Phase 6 commit `a917344dead3ba3260d74b6014cb38597fcd609a`; both origin URLs are `https://github.com/yashvardhanshah/AI-Legal-Evidence-Analysis-System.git`. The index is empty. No commit or push was performed. Phase 7 is complete for owner review; UI redesign and Phase 8 have not begun.


## Approved Phase 7 commit/push review - 2026-10-22

The owner reviewed Phase 7 and explicitly approved committing and normally pushing it to the existing public GitHub main branch, after exact-file review and one final staged-content secret scan. The existing **135 passed, 0 failed, 1 skipped**, two-warning, **738.56-second** full-suite result, preservation checks, browser verification and security results above are reused as requested. No application, migration, dependency, frontend or test changes were made during this approval review; only documentation was updated to record the owner's approval. Expensive tests and data/integrity scans are not repeated.

The reviewed publication scope remains exactly **28 paths (17 modified, 11 new)**: project source, additive migration, tests, dependency lock/configuration, ignore rules and documentation. Private PDFs/snapshots/evidence, model weights, datasets, actual .env/credentials, databases/volumes, browser profiles and temporary/generated outputs remain excluded. The actual staged blobs must pass the final local secret/artifact scan, including the 46 ignore probes and comparisons to actual local secrets, before committing. These custom checks are not a penetration-test or full dependency-CVE audit claim.

Branch main and both origin URLs were checked against `https://github.com/yashvardhanshah/AI-Legal-Evidence-Analysis-System.git`; a fresh fetch confirmed no divergence from the Phase 6 base. Approved message: `feat: add source-grounded investigation reports and review workflow`. No force push is authorized. Stop after the normal push, remote/local hash comparison and clean-tree confirmation; Phase 8 remains unauthorized. Earlier uncommitted-state statements are historical completion-review checkpoints.
