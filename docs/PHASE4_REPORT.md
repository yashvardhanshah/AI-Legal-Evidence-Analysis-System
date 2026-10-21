# Phase 4 verification report

Implementation report date: 2026-10-20. The owner has reviewed Phase 4 and approved its commit and push subject to final verification. The completion-review observations below are retained; approved pre-commit checks are recorded separately. Phase 5 is not authorized.

## Delivered implementation

The existing authenticated evidence workflow now queues PDF/PNG/JPEG analysis in PostgreSQL and returns immediately. A separate CPU worker extracts page text, performs real Tesseract OCR where required, runs the pinned offline DistilBERT NER model, adds literal date/time/document-reference mentions, and publishes immutable source-linked results. Existing uploads, originals, public judgment retrieval and semantic search remain available.

New source modules are `analysis_extraction.py`, `analysis_nlp.py`, `analysis_jobs.py`, `analysis_worker.py`, `analysis_api.py`, `ner_model.py` and the opt-in `verify_phase4.py`. The additive `0004_document_analysis.py` migration creates model/run/page/entity records, bounded job retry metadata and fenced leases. It does not reset existing data. Models and private artifacts stay outside Git. Existing models/config/router, Compose, case components and documentation are extended; `analysis.tsx` adds functional Analyze/View/status/retry/page text/entity highlighting without a UI redesign. `test_phase4.py` adds real-document and security regressions. The Phase 2 migration-head assertion is intentionally updated to the new head.

See [the design and endpoint reference](PHASE4_DESIGN.md) for all nine authenticated nested routes, schema constraints, limits, model versions/licenses/hashes and exact score semantics. Every route checks the current case and evidence relationship. Writes require CSRF and active-case write permission. Read-only researchers cannot trigger work; other users cannot retrieve results by substituting identifiers. The worker rechecks access during processing and before publication.

## Integrity and background processing

Original SHA-256 is checked before extraction and before publication. Page text has its own hash, Unicode offsets reproduce exact source slices, and derived JSON is stored separately with its own hash. Completed versions are immutable; failed/interrupted attempts remain traceable, and partial results cannot be downloaded as complete analyses. The worker uses SQL row/advisory locks, expiring fenced leases, subprocess deadlines and bounded retries; it exposes sanitized failures and status/progress rather than parser traces or private paths.

The resumed real-document review exposed fragmented WordPiece name grouping. Probabilities are now averaged per tokenizer word before BIO grouping, with explicit provenance and a regression on the actual source mention `Vidya Sagar`. This changes the pipeline version to `document-intelligence-v2`; prior v1 results remain intact. It does not imply that all names are recognized correctly.

One resumed full run returned **67 passed, 1 failed, 0 skipped**, with 2 warnings in **592.35 seconds**: the scanned-PDF success assertion failed. That run did not expose the sanitized job error code, so its exact cause is not claimed. After limiting Tesseract OpenMP threads to one and improving failure diagnostics, the focused PNG/JPEG/scanned-PDF rerun passed **3 tests, 0 failed, 0 skipped**, with 1 warning in **86.80 seconds**. The 45-second OCR timeout remains in place; limits were not relaxed to pass tests. The final full-suite result is recorded below.

## Final regression results

The complete Phase 1–4 suite passed **68 tests, 0 failed, 0 skipped**, with **2 non-failing upstream warnings**, in **280.73 seconds**. This comprises all 51 earlier tests and 17 Phase 4 cases, including parametrized genuine PNG/JPEG/scanned-PDF OCR. Tests verify independent embedded-text agreement, exact spans/hashes, role/case boundaries, hidden private job details, integrity failure, empty/unsupported documents, model integrity/page limits, completed artifact access, subword grouping, asynchronous queueing and limits, bounded manual retries, simulated OCR failure/retry, expired lease fencing and revoked access. PostgreSQL savepoint fixtures roll back their test records.

The warnings concern Starlette's httpx test adapter and Sentence Transformers' renamed dimension method. Linux production frontend build, Windows TypeScript, and real HTTP smoke checks passed, including liveness, PostgreSQL readiness, frontend proxy, dashboard HTML and eight built assets. Alembic reports `0004_document_analysis (head)` with no new upgrade operations; pip reports no broken requirements. These counts are observed results, not claims of general model accuracy.

## Real document demonstration and measured results

Source: the existing [1951 Supreme Court judgment PDF](https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com/data/pdf/year=1951/english/1951_1_676_681_EN.pdf), under the already reviewed CC BY 4.0 source declaration recorded in Phase 2. Its unchanged SHA-256 is `120be20f98d20d1b3d8e0280f103e81c43965e3d99fa6827d5915835f66e7dc5`. The image and scanned PDF are explicitly declared 180-DPI derivatives of its first page, not new or fabricated evidence. Existing Phase 3 authentication and case ownership are used through the Next.js proxy; credentials/receipts remain private.

All three final v2 jobs completed on their first attempt through the separate worker, with observed queued/processing/page-progress/completed transitions. The PDF processed all six pages; the two OCR derivatives each processed one. Authenticated original downloads, completed page text/entity spans, derived JSON downloads and logout passed. The three v1 jobs/runs were retained rather than overwritten.

| Sample | Method | Pages | Page 1 characters | Normalized character agreement | Actual Tesseract mean confidence | Exact person anchors |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Searchable PDF | pypdf embedded | 6 | 1,852 | 0.9986176389 | Not applicable | 1 / 6 |
| Source PNG | Tesseract English | 1 | 1,796 | 0.9497919556 | 90.7890468439 | 1 / 6 |
| Scanned PDF | PDFium + Tesseract English | 1 | 1,796 | 0.9509015257 | 91.1260812890 | 1 / 6 |

Embedded agreement uses independent PDFium text. OCR agreement uses the publisher PDF text layer, which has its own errors. These SequenceMatcher values measure normalized character agreement, not ground-truth CER or general accuracy. Confidence is the character-weighted mean of actual Tesseract word scores on a 0–100 scale; embedded text has null OCR confidence. Six manually identified person anchors are a narrow coverage check, not a full labeled evaluation set. Only `Vidya Sagar` matched in each sample. Other real names were missed, fragmented or assigned incorrect categories; human review is essential.

Actual page-1 source spans demonstrate both model and deterministic output:

| Sample | Text | Label / extractor | Unicode start:end | Recorded score |
| --- | --- | --- | --- | --- |
| Searchable PDF | Vidya Sagar | PERSON / NER | 621:632 | 0.9598646164 |
| Source PNG | Vidya Sagar | PERSON / NER | 601:612 | 0.8571159840 |
| Scanned PDF | Vidya Sagar | PERSON / NER | 601:612 | 0.8393058479 |
| Searchable PDF | May 24 | DATE / literal rule | 49:55 | null |
| Source PNG and scanned PDF | May 24 | DATE / literal rule | 41:47 | null |

NER scores are uncalibrated model output, not confidence in legal truth. The literal date does not infer a missing year. Page 1 produced 28 candidates for embedded text (17 organization, 3 person, 3 location, 1 date, 4 references), 20 for PNG (6 organization, 9 person, 1 date, 4 references), and 18 for scanned PDF (4 organization, 9 person, 1 date, 4 references). Counts include wrong model candidates; they are not validated facts.

The resumed browser integration was repeated against final v2 results using installed headless Edge and an isolated ignored profile. Login, actual case/evidence rendering, Analyze Evidence, View Analysis, 1,796 OCR characters, 20 entity rows, exact source highlighting and logout passed with **0 runtime exceptions**. This checks functional integration and escaping/highlighting, not the truth of each candidate. Private screenshots and browser receipts remain ignored.

## Persistence and preserved records

Graceful restarts of PostgreSQL, backend and worker were followed by health checks and `verify_phase4 --verify-existing`. All completed results remained retrievable through authorized HTTP, with original/text/artifact hashes and source spans checked again. A separate read-only integrity check produced identical before/after counts and job states:

| Preserved record/check | Observed result |
| --- | ---: |
| Users / cases | 2 / 2 |
| Judgments / SQL passages / Chroma embeddings | 50 / 3,834 / 3,834 |
| Evidence originals | 5 |
| Original files passing SHA-256 (judgments + evidence) | 55 / 55 |
| Derived artifacts passing SHA-256 | 6 / 6 |
| Analysis runs / page text hashes / exact entity spans | 6 / 16 / 428 |
| Retained live analysis jobs | 6 completed, all one attempt |

The five evidence records comprise the three existing Phase 3 records plus two declared Phase 4 public-source derivatives. Existing private user material was not analyzed or changed. Three v1 and three v2 runs account for the six retained analyses. No volume deletion, database reset, corpus ingestion or model re-download occurred on resume. The earlier Docker interruption also preserved the prior completed jobs. Backend/frontend/database/worker are healthy; migration exits successfully.

The pinned NER download totals 261,694,557 bytes across seven files, including the 260,803,668-byte safetensors weights; it was acquired under the earlier explicit approval and reused. Tesseract English traineddata is 4,113,088 bytes with SHA-256 `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`. Runtime model integrity verification and recorded SQL model references bind results to those local files. Versions, licenses, source links and the NER weight hash are recorded in [the model register](PHASE4_DESIGN.md#models-software-and-provenance).

## Safety and Git state at implementation review

The custom secret scan reviewed all **82 Git-eligible files**, checked the actual local database password, JWT key and verification-account password, and found **0 findings**. All **32 ignore probes passed**. Actual models, evidence originals, derived JSON, evaluation receipts, browser profiles/screenshots and logs remain ignored. No private/generated binary artifact is tracked or Git-eligible. Custom static checks parsed **34 Python files**, checked explicit authentication on **24 private routes**, and found no flagged dynamic execution, shell execution, disabled TLS verification or destructive Phase 3/4 migration operation. These are local pattern/AST/artifact checks, not Gitleaks, TruffleHog, a dependency CVE database or a penetration test.

At implementation review, all modified and untracked project paths were reviewed: **15 modified and 12 new files**. Changes comprise application source, additive migration, tests, configuration and documentation. Temporary debugging/browser/integrity scripts remained under ignored `.local`, not among those paths. `git diff --check` passed. The index was empty. Branch was `main`; origin was `https://github.com/yashvardhanshah/AI-Legal-Evidence-Analysis-System.git`; HEAD remained Phase 3 `e96ad94ae16988a9dc1ac1c0e964a0ebff6b0752`. The working tree was intentionally modified for review. No commit, push, remote change or Phase 5 work had occurred at that point.

The owner subsequently approved commit and push with message `feat: add OCR and NLP evidence analysis pipeline`, subject to final verification. The complete staged list and its actual blobs are checked before committing. Phase 5 remains unauthorized.

## Approved pre-commit test verification - 2026-10-21

The final full suite passed **68 tests, 0 failed, 0 skipped**, with **2 existing upstream warnings**, in **274.19 seconds**. All 42 backend files match the container being tested byte-for-byte. No application, test, authorization or UI code was changed during approval verification.

The interrupted initial approval run returned **67 passed, 1 failed, 0 skipped**, 2 warnings, in **418.37 seconds**: the case-authorization regression received 401 rather than expected 404 for another user's request. Its isolated rerun passed **1 test**, 0 failed/skipped, 1 warning, in **76.85 seconds**, then the full suite passed as recorded above. The cause remains undetermined; no assertion was weakened and the failure was not reproduced. This history does not change the measured NLP limitation: **1 of 6 checked person mentions** matched in each sample, without establishing general model accuracy.

The remote fetch and push URLs both identify the existing `yashvardhanshah/AI-Legal-Evidence-Analysis-System` repository, on branch `main`. Local and remote Phase 3 commits matched before staging. GitHub metadata still identifies the repository as **public**, covered by the owner's earlier explicit authorization to push to that public repository. No repository visibility change is performed.

Post-test integrity checks again verified all **50 judgments, 3,834 SQL passages, 3,834 Chroma embeddings and 55 original-file hashes**. Existing 2 users, 2 cases, 5 evidence records and all 6 completed jobs/runs remained intact, with 6 derived hashes, 16 page hashes and 428 exact entity spans verified. No database reset, corpus ingestion, model acquisition or original-file modification was performed. The reviewed selection contains exactly 27 project paths; private evidence, datasets, model weights, actual `.env`/credential files, browser profiles, temporary logs and generated artifacts are excluded. Source scans, ignore probes, exact staged-blob scanning and Git diff checks gate the approved commit and non-force push.

## Reproduce locally

Preserve the current `.env`, `.local/phase2` and PostgreSQL volume. The approved NER snapshot already exists; do not run acquisition again.

```powershell
docker compose build backend frontend
docker compose up --no-build --wait --wait-timeout 180
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
docker compose exec -T backend python -m pip check
docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_CORPUS_TESTS=1 backend python -m pytest -q -p no:cacheprovider
backend/.venv/Scripts/python.exe scripts/smoke.py
docker compose exec -T backend python -m app.verify_phase4 --verify-existing
```

The final command retrieves the existing private verification receipt and completed results without uploading or requeueing. `python -m app.verify_phase4` without that flag is the opt-in live queue demonstration; it reuses existing receipt evidence and queues only when a matching completed pipeline version is absent. On its very first run it uploads clearly declared derivatives of the existing authorized source. It does not download datasets or models.

Open http://localhost:3000, log in, open an authorized case, then select **Analyze Evidence** and **View Analysis**. Status and page progress come from the real worker. Select an entity to highlight its exact page text. PDFs, images, model files, receipts, browser profiles/screenshots and database files are ignored private runtime artifacts.

## Limitations

This is English document extraction and candidate entity detection, requiring human review. The news-trained NER model can miss or misclassify historical Indian names, organizations and locations, especially uppercase and OCR-corrupted text. Uncalibrated softmax scores are not correctness probabilities. Literal date/time/reference matches are not validated dates, case identities or applicable law. No findings or legal conclusions are generated.

Character agreement with publisher text is not a ground-truth OCR accuracy estimate: the publisher text layer contains visible errors. The small person-anchor evaluation is neither a complete annotation set nor precision/recall. Handwriting, multilingual text, complex layouts and skew remain limitations. Configured page, pixel, character, OCR and job limits fail explicitly. MP4 analysis remains unsupported in this phase.

Automated tests cover retry/fencing and access revocation; they do not establish exhaustive crash recovery under every OS/storage failure. SQL and filesystem publication are separate transactions, so an interrupted job can leave an unreferenced private derived artifact. Static checks are not a vulnerability database or penetration test. Browser verification covers the installed Edge environment only. Keep the current deployment local; public production hardening is outside this phase.
