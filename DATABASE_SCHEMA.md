# Database schema

## Implemented in Phase 1

PostgreSQL database `legal_evidence` with Alembic revision `0001_foundation`:

| Table | Fields / constraints | Purpose |
| --- | --- | --- |
| system_metadata | key varchar(64) primary key; value varchar(255) not null; created_at timestamptz not null with database timestamp | Stores `development_phase=1`; readiness verifies persistence |
| alembic_version | Alembic-managed revision primary key | Tracks installed schema |

No evidence, invented cases or domain statistics are seeded. Migrations run transactionally. Run `alembic upgrade head` from `backend/`; migration downgrades remove tables and require explicit authorization for any database containing valued data.

## Phase 2 design scope (not migrated)

Users and roles; cases and case_members; evidence and derived_artifacts; processing_jobs; document_extractions and extracted_entities; image_detections and video_detections; legal_provisions; judgments and judgment_passages; legal_recommendations; reports and report_reviews; audit_logs; dataset_sources.

Design must include UUID identities, foreign keys, UTC timestamps, ownership and membership indexes, constrained processing states, provenance, SHA-256 integrity, source/version tracking and explicit deletion policies. Large files remain outside PostgreSQL; vectors live in Chroma with passage references. Authorization and domain counts must be implemented together so metrics never leak other users' records.
