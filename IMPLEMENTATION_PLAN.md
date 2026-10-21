# Milestones

Each phase requires implementation, relevant tests, honest verification results, documentation and user review. Approval is required before every commit or push and before advancing phases.

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Repository hygiene, Next.js shell, FastAPI, PostgreSQL foundation, migration, Docker, health integration | Reviewed, committed and pushed as c571b3f |
| 2 | Domain schema, evidence storage, reviewed public sources, Chroma indexing | Reviewed, committed and pushed as 4800cea; statute acquisition remains gated |
| 3 | Authentication, roles, case-level access, case CRUD, secure uploads | Reviewed, committed and pushed as e96ad94; 51 tests passed |
| 4 | Real OCR, NLP, source passages, reviewed corrections | Reviewed, committed and pushed as b9f9fed; 68 tests passed at final verification |
| 5 | Licensed and validated image/video processing | Reviewed, committed and pushed as 37ed922; final 85 tests passed |
| 6 | Verified Indian provisions, judgments and semantic retrieval | Reviewed by owner; commit and push approved subject to final safety verification. 113 passed, 1 authentic-statute-data skip; official statutory ingestion remains gated pending verified rights/version metadata. See docs/PHASE6_REPORT.md |
| 7 | Grounded analysis, human review and versioned PDF reports | Planned |
| 8 | End-to-end validation, evaluation, security and deployment preparation | Planned |

Phases 1–5 are reviewed and pushed. The owner subsequently authorized Phase 6 through the attached development request. Preserve all earlier data and functionality. Reuse the installed Phase 5 image and local MiniLM; no new model/dependency acquisition or paid API is proposed. Official statute access, rights and legal-version metadata must be verified before ingestion; unavailable sources stay disabled. Keep evidence, datasets, models, credentials and runtime/private research artifacts ignored. The owner reviewed Phase 6 and approved its commit and normal push after final regression, data-preservation and staged-file safety checks. Stop after the successful push; UI redesign and Phase 7 remain unauthorized.
