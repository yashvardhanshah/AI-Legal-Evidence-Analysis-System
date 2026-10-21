# Phase 6 verification report

Date: 2026-10-21. Phase 6 has been reviewed, and the owner approved commit/push subject to final verification; statutory data verification remains gated as described below. UI redesign and Phase 7 remain unauthorized. This report distinguishes available functionality from the unresolved statutory-source gate; it does not claim legal recommendation accuracy.

## Scope and architecture

The existing local MiniLM/Chroma judgment corpus now supports legal-question/fact-pattern search with exact court/source filters, judgment year, source excerpts, original/passage hashes, page/character references, model revision and cosine distances. Ranking joins only committed matching SQL/vector provenance and returns distinct judgments. Up to 5,000 vector candidates are considered, covering the current 3,834-vector corpus; expansion beyond this bounded candidate budget requires separate evaluation. Distances are retrieval signals, not legal correctness probabilities.

Private research follows case authorization -> selected completed extraction spans or explicitly confirmed human input -> exact token-window queries -> real source retrieval -> retained input/source references -> attributed human review. Automatic NLP entities and CV detections are not used as established facts. Every extracted input is bound to its evidence, original SHA-256, completed analysis/page, exact offsets and immutable extraction JSON artifact. Originals/artifacts are verified before processing/publication. Queries use the existing 220-word-piece/32-overlap algorithm and a sixteen-window cap; limits fail explicitly rather than silently truncating text.

The separate `research-worker` reuses SQL jobs, session advisory locks, SKIP LOCKED claiming, lease UUID fencing, child process deadlines, three bounded attempts, progress, sanitized failures and retained attempt history. It runs as non-root with bounded CPU/memory/processes, read-only original/extraction/model mounts and local persistent Chroma access. The worker never downloads anything. Existing document and visual worker defaults are preserved. Failed/partial runs do not publish private inputs/results as complete research.

Source-only suggestions are deterministic prompts to inspect actual retrieved passages; review checklists identify information to verify, rather than inventing legal issues or conclusions. There is no Gemini/other provider integration and no external LLM, private-data transfer or paid API. No text instruction can override a language-model policy because no generative model is invoked. The injected-instruction query test verifies that such text remains a retrieval query, not an executable instruction; no LLM security evaluation is claimed.

## Official statutes: actual availability and rights limitation

**Imported sections: BNS 0; BNSS 0; BSA 0; IPC/CrPC/Indian Evidence Act 0.** No statute PDF or complete-Act dataset was downloaded; no statutory text was imported/indexed or used for a statutory model result. The new parser/index machinery is implemented but positive authentic-statute parsing/version/effective-date validation is blocked by source verification; it is explicitly skipped in tests.

The [old India Code landing page](https://www.indiacode.nic.in/) announces migration. The research browser could not reach the new site, but direct HTTPS reached `https://indiacode.gov.in/`, its public configuration and advertised public API. The landing/policy route returned a JavaScript shell; this is not a verified reuse policy. Public metadata search also returned section/rule records, so broad act-name hits were not accepted as complete verified Acts. The old act identifiers did not resolve through the attempted new public identifier endpoint. No restriction was bypassed. The [MHA policy](https://www.mha.gov.in/en/page/website-policy) requires reproduction permission; other attempted official policy/Gazette URLs were inaccessible. Neither public access nor government ownership is treated as a blanket license.

Candidate official identities and publication metadata are recorded in [SOURCES.md](../SOURCES.md). No current consolidated version, comprehensive amendments list, universal subsection commencement date, or IPC/BNS crosswalk is asserted. General Act commencement cannot substitute for section-specific notifications/exceptions or transitional application. The live public/case API therefore explicitly reports insufficient verified statutory sources. The existing licensed Supreme Court corpus is available independently of this gate.

The operator-only importer requires a verified source/access/reuse record; official HTTPS URL; bounded local PDF; original SHA-256; exact normalized page spans and span hashes; full-section boundary/heading review; publication/consolidation dates; per-section effective intervals, commencement references and applicability notes; explicit rights/amendment-review provenance. It validates actual source title, rejects overlaps/duplicates/hash/offset discrepancies, retains immutable versions and indexes token windows in a separate `chroma-statutes` directory/collection. It cannot enable a blocked source and contains no network acquisition. A trusted operator's legal-version review is necessary; the importer does not independently adjudicate rights or determine current applicable law.

## Database and APIs

Additive Alembic `0006_legal_research` follows `0005_visual_analysis` and adds six tables: `statute_versions`, `provision_passages`, `research_runs`, `research_inputs`, `research_results`, `research_reviews`. Existing legal provisions, sources, processing jobs, model registry, cases and evidence are reused. Restrictive foreign keys, version/attempt uniqueness, exact span bounds and exclusive judgment/statute source references apply. No old column/row is rewritten; destructive downgrade is disabled.

Public `GET /api/v1/research/statute-sources` exposes candidate/gate metadata; `POST /api/v1/research/search` searches real available sources with documented filters. Public searches never expose private research jobs. The earlier judgment APIs remain available.

Private paths under `/api/v1/cases/{case_id}`:

| Method/path | Function |
| --- | --- |
| GET /research-inputs | Paginated completed extraction previews with exact page/evidence references |
| POST /research-jobs | Validate selected spans/confirmed input, enqueue/reuse; `reanalyze:true` creates a new completed-request version |
| GET /research-jobs | Scoped paginated history/status |
| GET /research-jobs/{job_id} | Sanitized status and retained attempt metadata |
| POST /research-jobs/{job_id}/retry | Current-access, bounded manual retry with active-duplicate protection |
| GET /research-runs/{run_id} | Completed inputs, exact queries, real source passages, provenance and reviews |
| POST /research-runs/{run_id}/results/{result_id}/reviews | Append-only attributed relevance annotation |

Every private read checks current case access. Writes require active-case write access and investigator/lawyer/administrator role, including for otherwise unprivileged case owners; public registration still cannot assign a privileged role. CSRF and origin checks remain. Wrong case/job/run/result relationships return generic 404, missing authentication 401, read-only/privilege violations 403, partial runs 409. Saved citations are revalidated against actual source IDs, text/hash, URLs, offsets, source fields and model revision; saved queries must equal their recorded input substring. Responses remain no-store and never expose storage paths, credentials or leases.

Minimal frontend `/research` and case-page controls show genuine search results, source excerpts, selected extraction previews/offsets, actual queries, background status, outcome/limitations and review annotations. No cosmetic redesign or fabricated success response is introduced.

## Actual tests and integration observations

Initial focused Phase 6 run: **19 passed, 0 failed, 1 skipped**, 2 existing upstream warnings, **86.73 seconds**. After stronger source/reference/artifact checks, focused run: **26 passed, 0 failed, 1 skipped**, 2 warnings, **144.17 seconds**. The subsequent complete Phase 1–6 suite, including the additional queue/versioning cases, passed **113 tests, 0 failed, 1 skipped**, with **2 existing upstream warnings**, in **373.01 seconds**:

```powershell
docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_CORPUS_TESTS=1 backend python -m pytest -q -p no:cacheprovider
```

All 85 earlier tests remain. New tests cover real source retrieval/deduplication/filters; exact evidence/query/citation traceability; unprivileged ownership, CSRF, cross-case/private-history/read-only boundaries; source/offset/model URL tampering; independently retained extraction artifacts; attributed append-only reviews; insufficient inputs/sources; explicit confirmation; deterministic handling of instruction-shaped query text; stale fencing; current access revocation; retries/caps; request versioning/active deduplication; queue limits/archival; and blocked statute imports. PostgreSQL fixtures use rolled-back savepoints and genuine existing judgment/evidence records; controlled failure/tamper inputs are clearly negative fixtures, never published as authentic legal text/results.

The single skip is `test_authentic_statute_parsing_and_effective_dates_when_rights_verified`: actual statutory source rights/version metadata are not verified, so no synthetic legal text substitutes for authentic data. There is no measured legal relevance/applicability benchmark, no general recommendation accuracy or statutory-parser success claim. Existing warnings are Starlette TestClient's httpx adapter deprecation and the Sentence Transformers embedding-dimension rename.

All **58 backend files** matched the tested container. Windows TypeScript and the first production frontend build passed. The first real authorized worker job completed and citation checks succeeded, but its follow-up public search through the frontend proxy returned **404**: the proxy's existing route allowlist omitted `research`. That frontend-only allowlist omission was corrected, retaining the origin/path protections. The corrected production frontend build, TypeScript, real proxy and browser checks passed as recorded below; backend application/test code is unchanged from the successful complete suite.

## Models, dependencies and limits

The installed Apache-2.0 `sentence-transformers/all-MiniLM-L6-v2`, pinned revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, is reused locally with its eleven-file **91,578,415-byte** snapshot. No model, Python/Node dependency or legal dataset was downloaded. Cached Phase 5 image/layers were reused; no prior OCR/NER/YOLOX component was replaced. Model file hashes, license, software and registry reference are retained in research provenance. Existing English OCR/NER limitations remain, including Phase 4's measured **1 of 6 checked person mentions**, which is not general NER accuracy. Historical English judgments do not establish coverage of present-day Indian criminal law.

No facial identification, re-identification, guilt/liability/intent classifier or legal conclusion generator is added. Human-entered factual input and relevance annotations are attributed assertions, not verified truth. Search similarity and source authenticity do not prove relevance, binding authority, admissibility or applicability. OCR errors, missing context, later precedents, amendments, repeal, commencement exceptions and transitional provisions require human checking. Per-user/global queue count checks are application limits, not a cross-case global concurrency quota guarantee. Codec/browser/crash/security coverage is bounded; local static scans are not CVE or penetration testing. Keep the stack local and source/version review mandatory.

## Files and local commands

Created backend: `legal_retrieval.py`, `research_api.py`, `research_jobs.py`, `statute_ingestion.py`, `verify_phase6.py`, additive `0006_legal_research.py`, and `tests/test_phase6.py`. Created frontend: `/research/page.tsx`, `workspace/research.tsx`. Created documentation: this report and `PHASE6_DESIGN.md`. Extended models, worker dispatch, router/readiness, migration-head expectation, Compose, frontend proxy/case controls, ignore rules and existing model/source/schema/API/security/startup/testing documentation. Private verification receipts, source-policy metadata, logs, browser helpers/profiles and temporary build files remain under ignored `.local`.

Preserve the existing `.env`, `.local/phase2` and named PostgreSQL volume. The already built local services start without acquisition:

```powershell
docker compose up --no-build --wait --wait-timeout 180
docker compose ps --all
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
docker compose exec -T backend python -m pip check
backend/.venv/Scripts/python.exe scripts/smoke.py
docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_CORPUS_TESTS=1 backend python -m pytest -q -p no:cacheprovider
docker compose exec -T backend python -m app.verify_phase6 --preservation-only
docker compose exec -T backend python -m app.verify_phase6 --verify-existing
```

The actual cache-only backend build uses ignored `.local/phase6.Dockerfile` (`FROM legal-evidence-backend:phase5-base`, source COPY, non-root appuser), preserving installed dependencies:

```powershell
docker buildx build --file .local/phase6.Dockerfile --output 'type=image,name=legal-evidence-backend,compression=uncompressed,push=false,store=true' ./backend
docker compose build --pull=false frontend
```

This local helper/tag is not a committed dependency; fresh environments use the normal repository Dockerfile and require their own reviewed acquisition budget. `python -m app.verify_phase6 --run-flow` explicitly invokes the trusted local operator demonstration: it registers a dedicated reserved-domain integration identity, locally grants investigator role and membership of the existing genuine-source verification case, then uses real HTTP enqueue/retrieval/review/logout. No existing user role or case/evidence record is edited; credentials remain private. `--verify-existing` retrieves its saved job without creating an account or queueing work.

Future statute ingestion requires verified rights/access/version metadata first, then an approved local PDF and private review manifest. Only after that gate is satisfied:

```powershell
docker compose exec -T backend python -m app.statute_ingestion --manifest /private_data/statute-imports/reviewed-version.json
docker compose exec -T backend python -m app.statute_ingestion --index
```

These commands never download a file or grant source permission. They are currently data-gated. Stop services with `docker compose stop`; do not remove volumes or originals.

## Final real demonstration, preservation and repository safety

The authorized real worker demonstration used **700 exact extracted characters** from page 1 of existing genuine evidence, forming **one exact query window**. It completed in **one attempt**, retained **three source-linked judgment results** and an attributed `needs_verification` review, with **zero statutory results**. Recorded run wall time was **55.865305 seconds** (run creation to finish, excluding queue wait); this is a single local observation, not a general performance benchmark.

| Actual case-query source metadata | PDF page | Observed cosine distance |
| --- | --- | --- |
| LOGENDRA NATH JHA & OTHERS versus SHRI POLAILAL BISWAS | 1 | 0.107974470 |
| MANOHAR LAL versus THE STATE | 6 | 0.107974470 |
| BHIM SEN FOR R. S. MALIK MATHRA DAS versus THE STATE OF PUNJAB | 10 | 0.360848784 |

The first two distinct document records contain the same retrieved passage/distance. They are **not independent corroboration**. Judgment-ID deduplication does not eliminate repeated excerpts across different publisher records; source PDFs/context and metadata must be checked. `verified_source_text` denotes record/hash/provenance correspondence to the reviewed corpus, not court certification, OCR correctness, legal validity or independent factual confirmation. Private results retain the first matching source per document across ordered query windows; distances from different queries are not a calibrated global relevance ranking.

The actual public query **fundamental rights and equality before the law** returned five distinct judgment records; the first three were KESHAVAN MADHAVA MENON versus THE STATE OF BOMBAY (page 7, 0.384161711), THE STATE OF BOMBAY AND ANOTHER versus F. N. BALSARA (page 27, 0.416094840), and S. KRISHNAN AND OTHERS versus THE STATE OF MADRAS (page 32, 0.464016378). Each excerpt, original/passage hash, source URL, SQL ID and model reference was checked against actual source records. Full private input/output receipts stay ignored; no selected evidence text or credentials are reproduced here.

The final production frontend build and Windows TypeScript passed after the proxy correction. Installed hidden Edge passed real public search (five passages), investigator login, authorized extraction selection, enqueue/background completion, actual query/source display, saved human review and logout with **0 runtime exceptions** and no displayed research errors. The browser's 1,000-character selection generated **two query windows and four distinct source results**. Its initial ignored CDP harness attempted to serialize a React DOM node and failed with `Object reference chain is too long`; boolean wait expressions fixed only the harness, with no application change.

Before/after graceful PostgreSQL/backend/document-worker/visual-worker/research-worker restarts, all baseline domain-row fingerprints matched: **50 judgments; 3,834 SQL passages and Chroma embeddings; 2 original users and 2 existing cases; 7 evidence records; all 57 original hashes and 20 artifact hashes; 6 OCR/NLP runs, 16 pages, 428 entities; 2 vision runs, 7 visual frames and 84 detections**. The one new dedicated investigator account/membership and embedding registry record are deliberate verification additions; no original user role or case/evidence row was edited. The two new research runs, three retained input windows, seven source results and two annotations matched their exact pre-restart fingerprints. All **3,834 embedding contents/IDs/metadata** also matched a pre-restart aggregate SHA-256 checkpoint, beyond the count check. Authorized Phase 4/5/6 result and download verification passed after restart without uploading/reprocessing.

All six running services recovered healthy; migration remains additive head `0006_legal_research`, with no schema drift and no broken pip requirements. HTTP smoke checks passed liveness/readiness, frontend proxy/dashboard and eight built assets. The complete backend suite remains **113 passed, 0 failed, 1 deliberately gated statute-data skip**, 2 upstream warnings, **373.01 seconds**. No backend change followed that successful suite.

Final custom secret/ignore/static scans and Git review are recorded in TESTING.md. Model/data/private report/credential/browser/log files remain ignored; extensionless original and evidence blobs, separate statute Chroma data and private research/import folders have explicit ignore rules. No licensed binary, statutory text dataset, model weight, actual `.env`, uploaded evidence, browser profile or temporary helper is among the source changes. At the implementation-review checkpoint, no files were staged or committed/pushed, and the repository was on `main` at Phase 5 commit `37ed922ed6ba888c00eed942fa4b76ce2a298d52`. The owner subsequently approved the Phase 6 commit/push subject to the final checks recorded below. Phase 7 remains unauthorized.


## Approved Phase 6 pre-commit verification - 2026-10-21

The owner reviewed Phase 6 and approved its commit and normal push to the existing public GitHub repository, subject to final checks. The first approval rerun returned **112 passed, 1 failed, 1 skipped**, with **2 existing upstream warnings**, in **684.44 seconds**. The existing real-page OCR fallback test hit its unchanged **60-second Tesseract timeout**. The frontend build ran concurrently; no cause for the timeout was established. No timeout, assertion, backend behavior or access control was relaxed. The isolated unchanged OCR test subsequently passed **1 test, 0 failed, 0 skipped**, with **1 existing warning**, in **19.59 seconds**. A complete rerun was then performed without a concurrent frontend build; its final result is recorded below.

The production frontend build and Windows TypeScript check passed. The only application edit during approval verification makes the public and private research notices explicitly state that verified statutory recommendations are unavailable. The running frontend serves that notice, and its live statute-source API reports zero imported provisions. **Imported counts remain: BNS 0, BNSS 0, BSA 0 and legacy IPC/CrPC/Indian Evidence Act 0.** The authentic-statute parsing/effective-date test remains skipped because verified source rights and complete legal-version metadata are unavailable; no synthetic legal text substitutes for them. No UI redesign or Phase 7 work was performed.


The final complete regression rerun passed **113 tests, 0 failed, 1 skipped**, with **2 existing upstream warnings**, in **509.13 seconds (8 minutes 29 seconds)** using the full database/corpus-enabled command above. The unchanged OCR fallback test passed as part of this full suite. Both the earlier timeout and isolated pass are retained here rather than omitted from the verification history.

Final review covers **28 project paths (17 modified, 11 new)**: application source, the additive migration, tests, configuration and documentation. Custom secret/artifact scans of all **106 Git-eligible files** found **0 findings**, including comparisons against **four actual local secret values** without printing them; all **42 ignore probes** passed. Static checks parsed **49 Python files**, checked authentication on **39 private routes** and found no flagged destructive migration or private/generated file. These are custom pattern/AST checks, not a dependency-CVE audit or penetration test. The exact staged blobs are scanned again before the approved commit. No licensed model weights, original PDFs, images/videos, private evidence, datasets, actual environment files, local databases/volumes, browser profiles, temporary scripts/logs or generated outputs are included.

Branch `main` and both origin URLs match `https://github.com/yashvardhanshah/AI-Legal-Evidence-Analysis-System.git`. A fresh fetch confirmed no divergence from the reviewed Phase 5 base. The approved commit message is `feat: add evidence-grounded legal research and review workflows`; publication is authorized to this public repository. No force push, UI redesign or Phase 7 work is authorized.


After the final passing suite, read-only preservation verification again confirmed every pre-Phase-6 baseline row unchanged: **50 judgments, 3,834 SQL passages and Chroma embeddings, all 57 original-file hashes, 20 derived hashes, both existing cases, 7 evidence records, 6 OCR/NLP runs/16 pages/428 entities, and 2 visual runs/7 frames/84 detections**. The current approval verification also matched all embedding contents/IDs/metadata and the saved new research history against the private restart checkpoint. The intentionally added investigator account/membership and research/model records remain as documented; no existing record or original file was reset or replaced.
