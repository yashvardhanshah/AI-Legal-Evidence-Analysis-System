# Milestones

Each phase requires implementation, relevant tests, honest verification results, documentation and user review. Approval is required before every commit or push and before advancing phases.

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Repository hygiene, Next.js shell, FastAPI, PostgreSQL foundation, migration, Docker, health integration | Reviewed, committed and pushed as c571b3f |
| 2 | Domain schema, evidence storage, reviewed public sources, Chroma indexing | Reviewed, committed and pushed as 4800cea; statute acquisition remains gated |
| 3 | Authentication, roles, case-level access, case CRUD, secure uploads | Reviewed, committed and pushed as e96ad94; 51 tests passed |
| 4 | Real OCR, NLP, source passages, reviewed corrections | Reviewed, committed and pushed as b9f9fed; 68 tests passed at final verification |
| 5 | Licensed and validated image/video processing | Reviewed by owner; commit and push approved subject to final verification. 85 tests passed at implementation review; real image/video worker, browser, reference-runtime and restart/preservation checks complete. See docs/PHASE5_REPORT.md. Phase 6 is not authorized |
| 6 | Verified Indian provisions, judgments and semantic retrieval | Planned |
| 7 | Grounded analysis, human review and versioned PDF reports | Planned |
| 8 | End-to-end validation, evaluation, security and deployment preparation | Planned |

Phases 1–4 are reviewed and pushed. Phase 5 is explicitly authorized and extends the existing worker, storage and access policy without resetting data or replacing OCR/NLP. The owner approved the pinned 35,858,002-byte Apache-2.0 YOLOX-S model, OpenCV headless CPU wheel and two genuine licensed Wikimedia sources, then raised the network cap to 250 MB after an unexpected Python/OS cache refresh; the additional-disk cap remains 1 GB. Reuse the installed Phase 4 image to avoid ML dependency re-downloads. Keep evidence, datasets, models, credentials and all runtime artifacts ignored. Preserve all pre-existing original hashes, corpus counts and OCR/NLP rows/history. The owner has reviewed Phase 5 and approved its commit and normal push after final regression, preservation and staged-file safety checks. Stop after the successful push; UI redesign and Phase 6 remain unauthorized.
