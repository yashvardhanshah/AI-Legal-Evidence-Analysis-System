# Database schema

Additive revision `0002_legal_data` follows `0001_foundation`. It preserves both original tables and the `development_phase=1` row, adds `legal_data_schema=2`, and creates nine tables. No tables or existing data are dropped. Destructive downgrade is disabled; use reviewed forward migrations.

| Table | Keys, content and provenance |
| --- | --- |
| dataset_sources | UUID; unique slug; publisher, source/upstream URLs, license ID/URL, attribution, review status/timestamp and notes |
| judgments | UUID; source FK; unique (source, external ID) and SHA-256; nullable title/court/date/citation; source PDF/JSON URLs; private key, bytes/pages, extraction/pipeline version and JSONB provenance |
| judgment_passages | UUID; judgment FK; unique (judgment, ordinal); 1-based page, normalized-page character offsets, token count, actual text/hash; unique optional vector ID, embedding revision and indexed timestamp |
| legal_provisions | UUID; source FK; unique (source, act ID, version, provision ID); exact text; authoritative URL, original document hash/private key/page; optional effective dates; no inferred mappings |
| cases | UUID; unique user reference; title, description, jurisdiction, constrained active/archived status; no seeded cases or HTTP routes |
| evidence | UUID; case FK; unique (case, SHA-256); original filename, validated MIME, bytes, private key and provenance |
| evidence_artifacts | UUID; evidence FK; kind, separate key/hash/bytes and producer version; unique (evidence, kind, hash) |
| processing_jobs | UUID; optional source/judgment FKs; constrained lifecycle, attempts, total/progress, sanitized error code, JSONB outcomes and lifecycle timestamps |
| audit_logs | UUID; action, resource type/ID, operator actor label, non-secret JSONB details and timestamp |

All foreign keys restrict deletion. Creation/update timestamps are database-initialized; ORM updates refresh updated_at. Unique, page/offset, hash/size, status and progress constraints reject invalid records. Indexes cover source/judgment joins, court/date, case state, evidence hashes, jobs and audit resources/time. UUIDs are application-generated. Large files remain outside SQL; Chroma holds vectors keyed by passage UUID.

With `alembic_version` and `system_metadata`, there are eleven tables. Readiness accepts both known migration revisions. Users/roles/case membership, entities, detections and report/review tables remain later-phase work. No private case/evidence API is exposed before authorization exists. Corpus APIs omit private storage paths and raw metadata HTML.

Migration tests apply Phase 1 then Phase 2 twice inside a fresh isolated PostgreSQL schema in a rolled-back transaction, checking the preservation probe and new tables. They do not reset the real database.
