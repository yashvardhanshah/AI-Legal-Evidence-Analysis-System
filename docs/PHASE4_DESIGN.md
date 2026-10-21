# Phase 4 document intelligence design

This phase reuses the existing evidence, authentication, storage, SQL jobs and installed CPU dependencies. No corpus re-ingestion, Chroma changes, database reset or UI redesign is required. Processing is a separate service, never an API background thread or an upload handler.

## Models, software and provenance

| Component | Version/revision | License and acquisition |
| --- | --- | --- |
| dslim/distilbert-NER | `dfa2838a127384aabb82ed7719e16dab84c42a2a` | Publisher-declared Apache-2.0; owner approved up to 300 MB network / 600 MB temporary disk; exactly 261,694,557 bytes transferred across 7 files |
| NER safetensors | 260,803,668 bytes; SHA-256 `235ecd699f650ca36513b122d11ce5a80339be1388f06c33c2278368b99914e1` | Verified against the reviewed publisher LFS hash; no pickle/training weights/ONNX duplicate |
| Transformers / Torch | 4.57.6 / 2.9.1+cpu | Existing Apache-2.0 / BSD-3-Clause dependencies; no additional package download |
| Tesseract English | Engine 5.5.0; installed eng.traineddata hash/bytes recorded per run's model reference | Existing Apache-2.0 engine/traineddata; no new language-pack download |
| pypdf / pypdfium2 | 6.21.1 / 5.14.0 | Existing BSD-3-Clause / Apache-2.0-or-BSD-3-Clause wrapper, with bundled PDFium notices |
| Pillow | 12.3.0 | Existing HPND/PIL-style license |
| Literal extraction rules | `literal-references-v1` | Repository source; deterministic date/time/reference mentions with exact rule IDs, no invented scores or inferred years |

Official sources: [pinned NER files/card](https://huggingface.co/dslim/distilbert-NER/tree/dfa2838a127384aabb82ed7719e16dab84c42a2a), [Tesseract TSV](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html), [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast), [pypdf](https://github.com/py-pdf/pypdf), [pypdfium2](https://github.com/pypdfium2-team/pypdfium2).

NER snapshots/manifests stay under ignored `.local/phase2/models/ner/<revision>/`. Inference verifies local hashes, uses CPU and safetensors, `local_files_only=True` and `trust_remote_code=False`. No request triggers model acquisition or sends evidence externally. The explicit operator acquisition command requires the approved byte budget:

```powershell
docker compose exec -T backend python -m app.ner_model --root /private_data --approved-bytes 300000000
```

Use that only after approval and only if the snapshot is absent; existing verified files are reused. The seven files are card, config, safetensors, tokenizer/config/special-tokens and vocabulary. Per-file hashes and model identity/license are retained in the manifest and SQL model registry.

The English news-trained model retains PER→PERSON, ORG→ORGANIZATION and LOC→LOCATION; MISC is omitted. Fast-tokenizer overflow windows use 512 tokens with 64-token overlap, with no silent truncation. WordPiece probabilities are averaged per tokenizer word before BIO grouping; spans retain exact original page-text offsets; exact/contained overlap-window fragments are removed. Candidate scores are mean selected word-averaged BIO softmax values, uncalibrated and potentially wrong, especially for Indian names, historical spelling/capitalization and OCR artifacts. Dates/times/references are literal mentions, not verified dates, unique case identities, statute mappings or legal conclusions. Rule scores are null. No LLM summary or legal finding is generated.

## Extraction and integrity

Every attempt verifies original SHA-256 before parsing and again before publishing. Originals are never rewritten. Existing searchable PDF text uses pypdf per page; missing/short layers use PDFium rasterization and real Tesseract English TSV. PNG/JPEG use actual OCR with EXIF orientation applied only to the processing derivative. Text preserves line structure; recorded compatibility transformations are CRLF/CR→LF and NUL→U+FFFD. OCR text uses recognized TSV word order, spaces within lines and newlines between TSV lines. Word boxes refer to processed raster pixels, not original PDF font coordinates.

Each page stores exact text, SHA-256, method, page number and available OCR words/boxes/scores. Page OCR score is a character-weighted mean of available Tesseract word confidence (0–100); it is not calibrated accuracy. Embedded text has null OCR confidence. All entity/word offsets are zero-based Unicode code points within the persisted page, end exclusive, and slicing must reproduce the stored text. The browser also highlights by code point, including non-BMP characters.

Defaults: 50 pages, 1,000,000 document characters, 100,000 page characters, 180-DPI rendering up to 16 million pixels, 45-second OCR timeout, 600-second job timeout. Tesseract subprocesses use `OMP_THREAD_LIMIT=1` to bound CPU use and avoid OpenMP oversubscription in the local CPU container. Exceeding limits fails explicitly; nothing is silently truncated. Blank pages can be recorded with warnings; an entirely textless document fails without publishing entities. English OCR/NER, difficult layouts, skew, handwriting, multilingual documents and pre-existing publisher text errors limit reliability. Derived JSON is separate, immutable, content-addressed storage (bounded at 50 MB), referenced by existing `evidence_artifacts` rows and downloaded only through authorization/hash checks.

## Additive database schema

Revision `0004_document_analysis` follows `0003_private_workspace` and adds separate `document_analysis_schema=4`, preserving all earlier installation markers and rows. Destructive downgrade is disabled.

| Table | Content |
| --- | --- |
| analysis_models | Unique name/revision, task, license/source URL, exact byte size/file hashes/software snapshot |
| evidence_analyses | Restrictive evidence/job/model/artifact FKs, unique job/attempt, lifecycle, original hash, pipeline/settings, warnings and completion/error |
| analysis_pages | Unique analysis/page, text/hash, extraction method, optional actual OCR confidence/raster dimensions, word coordinates and warnings |
| analysis_entities | Restrictive page/model FKs, constrained supported labels, exact text/span, extractor, nullable score and rule/model provenance; unique page/label/span/extractor |

Existing `processing_jobs` gains nullable evidence/requester FKs, lease UUID/expiry, next-attempt timestamp and maximum attempts (default 3 for prior/new rows). A partial unique index permits one queued/processing analysis job per evidence. Existing public corpus job kinds/filtering remain unchanged. Models and files stay outside SQL; SQL binds results to exact immutable source versions.

## Durable worker and authorization

`worker` reuses the backend image, has no published port, runs non-root, and mounts only evidence originals read-only, NER models read-only and derived storage writable. It does not mount Chroma, public original PDFs, authentication keys or verification credentials. The Docker service has a 1,800-MiB memory limit, two CPU limit and process limit. SQL heartbeat health checks continue during child processing.

Claims use `FOR UPDATE SKIP LOCKED`, a session advisory lock held by the parent, bounded leases and per-claim tokens. Parsing/OCR/NLP run in a child process group, which is killed on timeout. Every progress/publication write checks the current lease and requesting user's current active-case write authorization. Retries use bounded delays/attempts and retain failed/interrupted versions; expired leases can recover after interruption. A stale process cannot publish over a new lease. Partial pages may persist for traceability but page/artifact APIs require a completed run. Logout does not cancel authorized durable work; membership revocation, inactive users or case archival prevent further publication.

Only owner/admin or assigned investigator/lawyer can trigger/retry on active cases. Assigned researchers can read completed results. Requests are cookie/CSRF protected using the existing policy. New analysis triggers check limits of three active jobs per requester and 100 globally in this local deployment; existing failed-job retries remain constrained by their own attempt cap and the one-active-job-per-evidence index. Failures expose fixed codes/messages, never parser traces, private text, paths or lease tokens. Audits contain IDs, hashes, attempt counts and error codes, not extracted content. Model inference is offline; the worker still needs its private PostgreSQL connection. File/SQL transactions are not one atomic transaction; an interrupted attempt can leave private unreferenced derived bytes, retained rather than automatically deleted.

## API and minimal frontend

All suffixes below start at `/api/v1/cases/{case_id}/evidence/{evidence_id}`. Every route rechecks authenticated case/evidence access; inaccessible IDs return generic 404. Mutations require CSRF and active-case write access. Public judgment/search routes remain public and never list private analysis jobs.

| Method and suffix | Behavior |
| --- | --- |
| POST /analysis | JSON `{reanalyze:false}`; queue/reuse active job with 202; matching completed job 200; explicit reanalyze creates a new version |
| GET /analysis-jobs | Scoped paginated history, status, page progress, attempt limit, sanitized message |
| GET /analysis-jobs/{job_id} | Scoped job and retained attempt metadata; no lease/storage keys |
| POST /analysis-jobs/{job_id}/retry | Requeue failed job below attempt cap, refusing conflicting active jobs |
| GET /analyses | Scoped paginated version/attempt/model metadata |
| GET /analyses/{analysis_id} | Run metadata; audited read |
| GET /analyses/{analysis_id}/pages | Completed page summaries; pagination |
| GET /analyses/{analysis_id}/pages/{page_number} | Completed page text/hash, OCR data and exact source-linked entity candidates; audited read |
| GET /analyses/{analysis_id}/download | Authorized hash-verified derived JSON attachment |

Unsupported/video documents return 422; partial/failed result reads 409; queue limits 429. Error codes cover invalid/unavailable/integrity/no-text/model/OCR/access and configured limits. Existing case pages add Analyze Evidence, status/progress/retry, View Analysis, page navigation and entity-to-source highlighting. Text/entity content is rendered as escaped React text, never raw HTML. No cosmetic redesign, upload blocking, automated corrections or Phase 5 visual processing is introduced.

## Evaluation policy

Use the already acquired CC BY 4.0 judgment and explicitly declared raster/scanned-PDF derivatives. Existing bytes are reused; no new dataset is downloaded. Compare embedded extraction with independent PDFium text; compare OCR with the publisher's embedded text layer while acknowledging that layer's visible OCR errors. SequenceMatcher normalized-character similarity is a descriptive agreement metric, not ground-truth CER or general accuracy. Six manually identified exact person mentions on that real page can measure limited anchor coverage; they are not injected into NLP results and do not establish complete NER precision/recall. Full observed results, exact commands, regression counts, restart checks and limitations belong in the Phase 4 report.
