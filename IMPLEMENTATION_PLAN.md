# Milestones

Each phase requires implementation, relevant tests, honest verification results, documentation and user review. Approval is required before every commit or push and before advancing phases.

| Phase | Scope | Status |
| --- | --- | --- |
| 1 | Repository hygiene, Next.js shell, FastAPI, PostgreSQL foundation, migration, Docker, health integration | Reviewed, committed and pushed as c571b3f |
| 2 | Domain schema, evidence storage, reviewed public sources, Chroma indexing | Reviewed, committed and pushed as 4800cea; statute acquisition remains gated |
| 3 | Authentication, roles, case-level access, case CRUD, secure uploads | Reviewed, committed and pushed as e96ad94; 51 tests passed |
| 4 | Real OCR, NLP, source passages, reviewed corrections | Owner reviewed; commit/push approved subject to final verification. 68 tests passed at implementation review; real worker/browser/restart checks complete. See docs/PHASE4_REPORT.md. Phase 5 is not authorized |
| 5 | Licensed and validated image/video processing | Planned |
| 6 | Verified Indian provisions, judgments and semantic retrieval | Planned |
| 7 | Grounded analysis, human review and versioned PDF reports | Planned |
| 8 | End-to-end validation, evaluation, security and deployment preparation | Planned |

Phases 1–3 are reviewed and pushed. Phase 4 implementation and its bounded 261,694,557-byte Apache-2.0 DistilBERT NER download (up to 300 MB network / 600 MB temporary disk) were explicitly authorized. Installed PDFium/pypdf, Tesseract, PyTorch and Transformers were reused. SQL extensions retain model/run/page/entity records and fenced job leases; processing runs in a separate PostgreSQL-backed worker, without Celery/Redis or new datasets. Exact source spans and actual OCR/model scores are preserved, current case access is required, and completed versioned results were evaluated using existing licensed source pages/declared derivatives. Keep originals, models and derived private artifacts out of Git. The owner reviewed Phase 4 and approved its commit and push subject to final tests, integrity verification and staged-content safety checks. Stop after the approved push; Phase 5 and UI redesign are not authorized.
