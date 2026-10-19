# Phase 1 API

Interactive OpenAPI: http://localhost:8000/docs; schema: `/openapi.json`.

| Endpoint | Success | Failure |
| --- | --- | --- |
| GET /api/v1/health/live | 200, status ok and service identifier | Process unavailable if API is stopped |
| GET /api/v1/health/ready | 200, database connected, migration 0001_foundation, phase 1 | 503, sanitized unavailable or schema_mismatch |
| GET /api/system (Next.js) | 200, sanitized backend readiness | 503 for upstream timeout, connection failure or unsuccessful readiness |

These are development health endpoints only. Domain APIs will be protected when authentication is implemented. No private records or secrets are returned. Frontend forwards only whitelisted readiness fields; driver messages and connection strings are never sent to clients.

## Phase 2 public corpus API

The existing health contract is preserved; readiness also accepts migration `0002_legal_data`. All endpoints below are loopback development endpoints over the public corpus. Cases, evidence, storage paths and ingestion writes are not exposed. An unavailable database returns sanitized 503 responses.

| Method and route | Behavior |
| --- | --- |
| GET /api/v1/dataset-sources | Reviewed source identity, license, access status, notes and actual judgment/indexed-passage counts |
| GET /api/v1/ingestion-jobs | Public corpus jobs only; limit 1–100 and nonnegative offset |
| GET /api/v1/ingestion-jobs/{uuid} | Public job state, progress, attempts, timestamps and sanitized error code; unknown/private jobs 404 |
| GET /api/v1/judgments | Optional literal title query q; paginated results and real total |
| GET /api/v1/judgments/{uuid} | Source metadata, hash, extraction method and paginated actual passages with page/offset/hash provenance |
| POST /api/v1/search/judgments | JSON query (3–1000 characters, no more than 256 model tokens) and limit (1–20); local normalized embeddings; cosine distance with lower_is_better=true; SQL-backed excerpts and source links |
| GET /api/v1/legal-provisions | Literal substring q with exact optional act/version filters; paginated real results; no inferred section mappings |

Search returns 503 when model/index dependencies are unavailable, 422 for invalid/oversized queries, and an honest empty result for an empty corpus. Missing judgment dates/titles/citations are null. Distances are retrieval outputs, not legal conclusions or evaluated relevance scores. The statute endpoint can return an empty list while source reuse verification is pending.

Judgment search groups a bounded set of retrieved passages by document and returns the best matching passage per distinct judgment. Each distance belongs to that passage; it is not an aggregate document score. The API returns up to the requested number of distinct judgments, preserving vector rank and checking SQL/hash/revision provenance.

Ingestion, source registration, evidence preservation and verified provision imports are CLI-only trusted local operator functions. They will need authenticated role/case checks before becoming HTTP workflows in Phase 3.
