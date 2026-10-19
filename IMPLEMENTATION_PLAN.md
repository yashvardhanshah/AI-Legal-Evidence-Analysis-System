# Milestones

Each phase requires implementation, relevant tests, honest verification results, documentation and user review. Approval is required before every commit or push and before advancing phases.

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Repository hygiene, Next.js shell, FastAPI, PostgreSQL foundation, migration, Docker, health integration | Reviewed, committed and pushed as c571b3f |
| 2 | Domain schema, evidence storage, reviewed public sources, Chroma indexing | Reviewed, committed and pushed as 4800cea; statute acquisition remains gated |
| 3 | Authentication, roles, case-level access, case CRUD, secure uploads | Manually reviewed by owner; commit/push approved after final verification; 51 tests passed again |
| 4 | Real OCR, NLP, source passages, reviewed corrections | Planned |
| 5 | Licensed and validated image/video processing | Planned |
| 6 | Verified Indian provisions, judgments and semantic retrieval | Planned |
| 7 | Grounded analysis, human review and versioned PDF reports | Planned |
| 8 | End-to-end validation, evaluation, security and deployment preparation | Planned |

Phase 2 uses additive migrations and preserves the Phase 1 installation state. Its bounded data, pinned model and CPU dependency downloads were explicitly approved. Chroma is a persistent embedded library. Phase 3 is now authorized and extends the existing schema without resetting or re-downloading data. Only owner-authorized verification metadata and genuine licensed-source copies may be used for the live flow. Celery/Redis remain later-phase work. Stop after Phase 3 verification; no commit, push or Phase 4 work is authorized.
