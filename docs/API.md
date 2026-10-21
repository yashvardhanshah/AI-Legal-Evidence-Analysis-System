# Phase 1 API

Phase 5 adds eight authenticated case/evidence visual command/result/artifact routes, listed in [PHASE5_DESIGN.md](PHASE5_DESIGN.md#api-and-access-policy). Readiness accepts additive head `0005_visual_analysis`; the earlier public judgment/search routes remain available under the existing policy.

Phase 4 document-analysis endpoints and score/offset semantics are listed in [PHASE4_DESIGN.md](PHASE4_DESIGN.md). All are nested under existing private case/evidence paths and preserve the Phase 3 authentication policy. Readiness now accepts additive head `0004_document_analysis`.

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

Corpus ingestion, source registration and verified provision imports remain trusted local operator functions. Private evidence preservation now uses the authorized Phase 3 routes below.

## Phase 3 private workspace API

Readiness also accepts `0003_private_workspace`. Browser requests use the same-origin Next.js `/api/backend/{path}` proxy, mapping to FastAPI `/api/v1/{path}`. Get `/auth/csrf` before registration/login and send its readable `legal_csrf` cookie value as `X-CSRF-Token` on mutations. Cookies are sent automatically; JWTs are HttpOnly and never returned in JSON. See [SECURITY.md](SECURITY.md) for roles, expiry, CSRF, archive and public-access policy.

| Method and path after `/api/v1` | Behavior |
| --- | --- |
| GET /auth/csrf | Issue/preserve a readable CSRF cookie; no authentication required |
| POST /auth/register | JSON email/display_name/password; fixed legal_researcher role; 201, no automatic login |
| POST /auth/login | JSON email/password; issue cookie access/refresh JWTs; return sanitized user and expiry |
| GET /auth/me | Current authenticated user, never a password hash or JWT |
| POST /auth/refresh | Rotate refresh JWT and CSRF cookie; retain absolute session expiry |
| POST /auth/logout | Revoke session and clear cookies, including when access has expired |
| GET /workspace/settings | Authenticated upload format/size/video limits |
| POST /cases | JSON title, description, jurisdiction, optional opened_on/incident_on; owner assigned from session; unique UUID/reference; 201 |
| GET /cases | Authorized cases only; literal q, active/archived status, limit 1–100, offset and actual total |
| GET /cases/{case_id} | Authorized case metadata and can_write/can_manage capabilities; audited read |
| PATCH /cases/{case_id} | Update supplied title/description/jurisdiction/opened_on/incident_on on an active writable case |
| POST /cases/{case_id}/archive | Owner/admin marks read-only; preserves metadata and originals |
| GET, POST /cases/{case_id}/members | Owner/admin lists or grants membership to a registered email |
| DELETE /cases/{case_id}/members/{user_id} | Owner/admin revokes membership; never deletes the user/case/evidence |
| GET /cases/{case_id}/evidence | Authorized paginated metadata and actual total |
| POST /cases/{case_id}/evidence | Raw binary request body; required query filename and provenance, optional ISO captured_on; validated immutable original; 201 |
| GET /cases/{case_id}/evidence/{evidence_id} | Authorized metadata; no storage key |
| GET /cases/{case_id}/evidence/{evidence_id}/download | Recheck case access/hash; attachment, no-store, X-Content-SHA256; audited download |
| GET /cases/{case_id}/audit | Owner/admin recent case audit events; limit/offset |
| PATCH /admin/users/{user_id}/role | Administrator-only role change; revokes target sessions; self changes disabled |

Missing/invalid authentication returns 401; missing/incorrect CSRF or forbidden role returns 403; inaccessible cases/evidence return generic 404; archived writes, duplicate originals or integrity failures return 409; actual oversized bodies return 413; field/format failures return sanitized 422; throttling returns 429. Storage failures return sanitized 503. Validation errors omit submitted inputs, including passwords. No case/evidence deletion or static storage route exists. Use the upload body directly (`fetch(url, {method: 'POST', body: file, headers: {'X-CSRF-Token': csrf}})`); this endpoint does not parse multipart forms.
