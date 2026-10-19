# Phase 1 API

Interactive OpenAPI: http://localhost:8000/docs; schema: `/openapi.json`.

| Endpoint | Success | Failure |
| --- | --- | --- |
| GET /api/v1/health/live | 200, status ok and service identifier | Process unavailable if API is stopped |
| GET /api/v1/health/ready | 200, database connected, migration 0001_foundation, phase 1 | 503, sanitized unavailable or schema_mismatch |
| GET /api/system (Next.js) | 200, sanitized backend readiness | 503 for upstream timeout, connection failure or unsuccessful readiness |

These are development health endpoints only. Domain APIs will be protected when authentication is implemented. No private records or secrets are returned. Frontend forwards only whitelisted readiness fields; driver messages and connection strings are never sent to clients.
