# Milestones

Each phase requires implementation, relevant tests, honest verification results, documentation and user review. Approval is required before every commit or push and before advancing phases.

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Repository hygiene, Next.js shell, FastAPI, PostgreSQL foundation, migration, Docker, health integration | Reviewed, committed and pushed as c571b3f |
| 2 | Domain schema, evidence storage, reviewed public sources, Chroma indexing | Judgment pipeline implemented and verified: 50 documents / 3,834 vectors / 29 tests passed; statute acquisition gated; awaiting owner review |
| 3 | Authentication, roles, case-level access, case CRUD, secure uploads | Planned |
| 4 | Real OCR, NLP, source passages, reviewed corrections | Planned |
| 5 | Licensed and validated image/video processing | Planned |
| 6 | Verified Indian provisions, judgments and semantic retrieval | Planned |
| 7 | Grounded analysis, human review and versioned PDF reports | Planned |
| 8 | End-to-end validation, evaluation, security and deployment preparation | Planned |

Phase 2 uses additive migrations and preserves the Phase 1 installation state. Its bounded data, pinned model and CPU dependency downloads were explicitly approved. Chroma is a persistent embedded library. Cases/evidence are not seeded, and their APIs await Phase 3 authorization. Celery/Redis remain later-phase work. Stop after Phase 2 for review; no commit, push or Phase 3 work is authorized.
