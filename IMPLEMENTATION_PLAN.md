# Milestones

Each phase requires implementation, relevant tests, honest verification results, documentation and user review. Approval is required before every commit or push and before advancing phases.

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Repository hygiene, Next.js shell, FastAPI, PostgreSQL foundation, migration, Docker, health integration | Implemented and verified natively and in Docker; awaiting user review |
| 2 | Domain schema, evidence storage, reviewed public sources, Chroma indexing | Awaiting approval |
| 3 | Authentication, roles, case-level access, case CRUD, secure uploads | Planned |
| 4 | Real OCR, NLP, source passages, reviewed corrections | Planned |
| 5 | Licensed and validated image/video processing | Planned |
| 6 | Verified Indian provisions, judgments and semantic retrieval | Planned |
| 7 | Grounded analysis, human review and versioned PDF reports | Planned |
| 8 | End-to-end validation, evaluation, security and deployment preparation | Planned |

Phase 1 intentionally creates only installation metadata. Full case/evidence schema and data ingestion belong to Phase 2. Celery, Redis and Chroma are planned with the pipelines that use them; no idle services or advertised AI functions are included now.
