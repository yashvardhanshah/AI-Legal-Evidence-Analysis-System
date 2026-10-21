# Phase 5 verification report

Date: 2026-10-21. **Implementation reviewed; owner approved commit and push subject to final verification.** UI redesign and Phase 6 remain unauthorized. The measured results below describe this local CPU verification, not general model accuracy.

## Delivered architecture

The private case/evidence workflow now supports real local YOLOX object detection for JPEG/PNG and sampled MP4 frames. `visual_model.py` pins and verifies model acquisition; `visual_inference.py` handles orientation, letterboxing, real OpenCV DNN inference, class-aware NMS, frame timestamps and annotations; `visual_jobs.py` retains fenced attempts and source hashes; `visual_api.py` scopes commands/results/artifacts to authenticated cases. The existing worker accepts `--kind visual_analysis`, with a separate visual-worker service, heartbeat and read-only source/model mounts. Its default document path remains unchanged. No upload/API request runs inference.

Additive Alembic revision `0005_visual_analysis` adds visual analyses, sampled frames, detections and the active-visual-job index, reusing existing model/job/artifact tables and preserving restrictive foreign keys. No original evidence is changed; derived source PNG and annotated PNG artifacts have separate hashes. Model settings, dimensions, source hash, frame index, presentation timestamp, output index, raw output hash, original model-space box, objectness, class probability and transformed/clipped source-pixel coordinates bind candidates to their source.

The existing case page adds Analyze Image, Analyze Video and View Results with actual job statuses, retained versions, sampled-frame navigation, authenticated hash-verified source/annotated image blobs and detection tables. There is no UI redesign. The eight new endpoints, role policy, limits and exact coordinate/timestamp semantics are documented in [PHASE5_DESIGN.md](PHASE5_DESIGN.md).

## Model, software and authentic source provenance

Model: OpenCV Zoo YOLOX-S, 80 COCO classes, Apache-2.0. Source revision `48b10fa505aeb51fbd127fc60a5c660040e823b7`; pinned official mirror revision `d4938dfc9d4ec5d098bfa33e98b3f3345a236586`. ONNX size **35,858,002 bytes**, SHA-256 `c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063`, verified after download and before local use. The publisher states that all files in [the model directory](https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_yolox) are Apache-2.0. Megvii copyright and [the full license](licenses/YOLOX-APACHE-2.0.md) are retained for the adapted reference conventions. No pickle, remote executable model code or inference API is used.

OpenCV: `opencv-python-headless==5.0.0.93`, hash-pinned CPU wheel, **61,204,038 bytes** for installed Linux x86_64/manylinux_2_28; wheel SHA-256 `ed709fdf9aa0bd1f2ed8549e71d19449b03a675bb581eb292285f6861953be37`. Existing NumPy 2.5.4 and ONNX Runtime 1.31.0 are reused. Pip installs only the new wheel with `--no-deps --require-hashes`; no existing ML library is upgraded or replaced. OpenCV 5 reports that explicit DNN targets are unsupported by its new graph engine; the installed CPU-only package executes inference locally. No GPU acceleration is claimed.

The owner approved bounded model/dependency/source downloads and later raised the total network cap from 130 MB to 250 MB. An initial ordinary Docker build unexpectedly refreshed Python/OS layers; it was cancelled while inspecting dependency metadata, before bulk ML package downloads. A local ignored incremental Dockerfile reuses the installed Phase 4 image and adds only the pinned OpenCV wheel/source. Logs record those actual events; no exact total wire-byte counter is claimed. Model and source payloads were acquired once and retained for reuse.

The installed backend image is 2,369,312,997 bytes versus 2,209,588,452 for the preserved Phase 4 base: a measured **159,724,545-byte logical image increase**. This is not a whole-host Docker/cache disk-usage measurement. The initially refreshed Python/OS layers and temporary caches are separate from that comparison; the ordinary build was stopped before bulk ML package downloads, and no existing data/model snapshot was re-downloaded.

| Authentic source | Attribution / license | Downloaded bytes / SHA-256 |
| --- | --- | --- |
| [YellowLabradorLooking.jpg](https://commons.wikimedia.org/wiki/File:YellowLabradorLooking.jpg) | Elf photograph, color revision by Carla Nunziata; CC BY-SA 3.0; original-file variant with owner retained; color revision disclosed, 700x577 | 140,606 / `ea1daaac9860befcbeb11b65c2d7da2a71c74d06c345dbc205f0b41797023425` |
| [Jijiga.ogv](https://commons.wikimedia.org/wiki/File:Jijiga.ogv) | Brian Dell, own traffic footage, 5 January 2011; CC0 1.0, 1920x1080, about 12 seconds | 18,214,298 / `2c75b1ae879ebfadb7473d24e29b34c072430cabe8f0b5e5e68f68e58ab372d2` |
| Local MP4 derivative of full Jijiga footage | Explicit H.264/960-wide/CRF23/no-audio transcode; retains genuine source frames, CC0 1.0; not described as camera-original MP4 | 2,563,991 / `286fe2b29d13f9b174dcdc665f734ee64de9cdbe82010e7bb8f8972c00b6b80f` |

Acquisition verifies pinned publisher SHA-1/version and byte sizes for the original Wikimedia media, then records independent SHA-256. Original OGV/photo and provenance remain under ignored private test storage. Annotation derivatives of the photograph retain CC BY-SA attribution/share-alike requirements when shared. No media/model file is Git-eligible. The opt-in acquisition helper does not run on uploads or inference.

## Exact test and integration results

The new Phase 5 module passed **17 tests, 0 failed, 0 skipped**, with one existing upstream warning, in **72.12 seconds**. The subsequent complete Phase 1–5 suite passed **85 tests, 0 failed, 0 skipped**, with **2 existing upstream warnings**, in **288.28 seconds**:

```powershell
docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_CORPUS_TESTS=1 backend python -m pytest -q -p no:cacheprovider
```

The 68 earlier cases remain. New cases cover actual JPG/JPEG/PNG dog detection, dimensions/bounds/confidence products, original and artifact hashes, independent ONNX Runtime coordinates, video indices/presentation timestamps versus independent ffprobe, authentication/CSRF/cross-case/read-only-role boundaries, private job history, wrong frame/run IDs, active/completed deduplication, explicit versioning, corruption, controlled retry/fencing/revocation, unsupported/malformed formats, model/pixel/frame/duration limits, asynchronous enqueueing, artifact tampering, manual retry exhaustion, queue limits and archival. SQL fixtures use savepoints and roll back their test records. Failure/retry/revocation tests inject explicit controlled failures; they do not fabricate successful detections or claim exhaustive crash testing.

Warnings are the existing Starlette httpx test-adapter deprecation and Sentence Transformers dimension-method rename. Production frontend build and Windows TypeScript passed. Alembic reports `0005_visual_analysis (head)` and no new upgrade operations; pip reports no broken requirements. HTTP smoke checks passed for liveness, PostgreSQL readiness, Next.js proxy, case-workspace dashboard and eight built assets. All **51 backend files** match the tested container byte-for-byte.

Installed headless Edge verified login, Analyze Image, Analyze Video, View Results, private blob image URLs, hash-verified source/annotated rendering, real detection tables, sampled-frame navigation and logout with **0 runtime exceptions**. The photo rendered at its actual 700x577 dimensions with one dog row; video frames rendered at 960x540 with 12 candidate rows on the first frame, then navigated to frame 60 at 2,002 ms. A screenshot was visually inspected to confirm the actual rendered dog annotation. The initial browser harness stopped at an incorrect Logout selector; only the ignored harness was corrected, and the complete rerun passed. No application/UI change was needed for that correction. Browser screenshots/profiles/receipts remain private and ignored; broader browser/device testing is not claimed.

## Real end-to-end demonstration and measurements

The opt-in flow used the existing authorized verification case and authenticated Next.js proxy:

**Login → Upload the genuine photo and declared MP4 derivative → Queue visual jobs → Separate worker inference → Save frames/detections/artifacts → Authorized retrieval and SHA-256/pixel checks → Logout.**

Both actual jobs completed in **one attempt**. The image flow observed processing/completed states; video polling observed queued, processing with increasing sample progress, and completed. Source downloads matched original encoded SHA-256, decoded unannotated PNG pixels matched their stored BGR pixel hashes, all annotated/source artifact hashes passed, and every candidate's class, confidence product and source bounds were checked. Model identity/hash was read from the actual SQL-backed result metadata.

| Sample | Actual result | Measured local forward time | Job wall time |
| --- | --- | --- | --- |
| Labrador image, 700x577 | 1 dog candidate, class index 16, score 0.8924898505; source-pixel box `[47.6376432180, 25.7224845886, 630.0923627615, 548.8188695908]` | 407.2501 ms | 9.2607 s |
| Jijiga MP4 derivative, 960x540 | 6 sampled frames; 83 candidate occurrences across samples: 53 person, 11 car, 16 truck, 3 bus | min 401.1899 ms / mean 833.2707 ms / max 1,419.9043 ms | 14.9224 s |

Forward timings measure only the model `setInput/forward` section and exclude preprocessing/postprocessing, model setup, decoding, SQL and artifact retrieval. Job wall time includes worker setup and publication. They vary with local load and do not establish a general FPS benchmark or production capacity. No mAP, ground-truth precision/recall or general accuracy is claimed. The one visible dog anchor is a narrow authentic-source check; video labels remain unreviewed candidates, not verified identities or unique counts.

The MP4 contains **343 frames at 29.9700299700 fps**, with metadata-derived duration **11.4447666667 seconds** (the public source page rounds its displayed length). Actual retained samples were:

| Decoded frame index | Actual elapsed presentation timestamp (ms) |
| ---: | ---: |
| 0 | 0 |
| 60 | 2,002 |
| 120 | 4,004 |
| 180 | 6,006 |
| 240 | 8,008 |
| 300 | 10,010 |

All six timestamps matched independent ffprobe within the asserted 0.05-ms tolerance. Nothing is inferred between those samples. An additional read-only ONNX Runtime comparison covered **all 84 stored image/video candidates**, with matching class indices. Observed maximum coordinate difference: **0.0000638999 pixels** for the photo and **0.0000922009 pixels** for video; maximum confidence difference: **0.000000119209** and **0.000003665686** respectively. These compare the emitted proposal indices, independently decoded boxes and score products using the same preprocessed input, not a manually annotated truth set. Acceptance tolerances were 0.05 pixels and 0.0002 score units; these tolerances are distinct from the measured differences.

Independent ffprobe decoding also confirmed that the downloaded OGV and declared MP4 each contain **343 frames at 30000/1001 fps**, with reported duration 11.444767 seconds. The transcode changes encoded format, scale and audio handling; it is not represented as a camera-original file.

## Preservation and restart persistence

Before migration, a private baseline fingerprinted every existing judgment, passage, case, evidence/artifact, model, processing job and OCR/NLP run/page/entity row. All those original row fingerprints still match after tests, uploads, inference, API/browser retrieval and graceful PostgreSQL/backend/document-worker/visual-worker restarts. Existing result IDs and artifacts were retrieved again using `--verify-existing`, without uploading or requeueing. No database volume was reset or removed, and no original file was overwritten.

| Record/check | Preserved baseline | Final observed state |
| --- | ---: | ---: |
| Judgments / SQL passages / Chroma embeddings | 50 / 3,834 / 3,834 | 50 / 3,834 / 3,834 |
| Cases | 2 | 2, original rows unchanged |
| Evidence originals / verified SHA-256 rows | 5 / 55 judgment+evidence originals | 7 / 57, all hashes verified; prior 55 intact |
| Existing OCR/NLP runs / pages / entities | 6 / 16 / 428 | 6 / 16 / 428, all original row fingerprints unchanged |
| Processing jobs | 9 | 11, prior 9 unchanged plus 2 completed visual jobs |
| Model records | 2 | 3, prior models unchanged plus pinned YOLOX |
| Artifact rows / verified hashes | 6 | 20, all hashes verified; prior 6 unchanged |

The two added evidence records are explicitly attributed public-source verification media in the authorized existing case. Existing private user evidence was not analyzed. The 14 new artifact rows represent source and annotated PNGs for one image plus six sampled video frames. Annotated images may contain model mistakes; they remain separate derivatives. All five long-running services are healthy after restart; migration exits successfully. No active visual job is left behind by verification.

The authorized Phase 4 HTTP verification was run again after Phase 5 restarts. Existing PDF/image OCR/NLP versions, exact source spans, original hashes and derived downloads remained accessible without reprocessing or requeueing. Its previously measured NLP limitation remains documented in the Phase 4 report; Phase 5 does not claim to improve that model's accuracy.

## Final security, repository review and remaining limits

The final custom secret scan reviewed **95 Git-eligible files**, including checks for the actual local database password, JWT key and verification-account password, with **0 findings**. All **36 ignore probes passed**, including added OGV/OGG/wheel/test-media exclusions. Actual model/media/evidence/derived/auth/browser/log paths are ignored. Custom static checks parsed **42 Python files** and confirmed explicit authentication on all **32 private case/document/visual routes**, with no flagged dynamic execution, enabled shell execution, disabled TLS verification, destructive Phase 3/4/5 migration or private/generated Git-eligible artifact. These are pattern/AST/artifact checks, not a dependency CVE database, Gitleaks, TruffleHog or a penetration test.

All **31 changed paths** were reviewed: 18 modified and 13 new files. They contain application source, the additive migration, tests, hash-pinned dependency configuration, the Apache-2.0 notice, Compose/configuration templates and documentation. Temporary browser/reference/build helpers and logs remain under ignored `.local`; no debugging script or private binary is among the project changes. `git diff --check` passed. At the implementation-review checkpoint, the index was empty. Branch was `main`, origin was `https://github.com/yashvardhanshah/AI-Legal-Evidence-Analysis-System.git`, and HEAD was Phase 4 `b9f9fed4a36ff70bb9deb4215eddf4c61bcb08d8`. The working tree was intentionally modified for that review; no Phase 5 commit, push or Phase 6 work had occurred at that checkpoint.

No production security or comprehensive codec/cross-browser/crash matrix is claimed. English OCR/NLP models and visual COCO candidates retain their earlier limitations. Images are converted to RGB for inference; alpha/ICC/color metadata are not retained in derivatives, and forensic color fidelity is not claimed. EXIF/video rotation applies only to decoded derivatives. Authentication and source hashes establish access/provenance, not truth of a detection. Preserve and review the immutable original alongside every derived result. The owner subsequently approved this Phase 5 commit/push, conditional on the final checks recorded below. Phase 6 requires separate explicit owner approval.

## Startup and exact verification commands

For this configured workspace, retain `.env`, `.local/phase2` and the PostgreSQL volume. Existing weights, licensed media and CPU dependencies are already present; do not run acquisition again.

```powershell
docker compose up --no-build --wait --wait-timeout 180
docker compose ps -a
docker compose exec -T backend alembic current
docker compose exec -T backend alembic check
docker compose exec -T backend python -m pip check
docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_CORPUS_TESTS=1 backend python -m pytest -q -p no:cacheprovider
backend/.venv/Scripts/python.exe scripts/smoke.py
docker compose exec -T backend python -m app.verify_phase5 --preservation-only
docker compose exec -T backend python -m app.verify_phase5 --verify-existing
```

Open http://localhost:3000, log in, open an authorized case, and use Analyze Image/Analyze Video then View Results. `python -m app.verify_phase5` without flags is the opt-in genuine-media upload/queue demonstration; it reuses its existing receipt/evidence and completed matching results. The receipt depends on the existing private Phase 3 verification account. It never acquires external media/models or sends evidence externally.

The actual bounded build reused a preserved local Phase 4 image tag with this ignored helper:

```powershell
docker buildx build --file .local/phase5.Dockerfile --output 'type=image,name=legal-evidence-backend,compression=uncompressed,push=false,store=true' ./backend
docker compose build frontend
```

That local helper starts from `legal-evidence-backend:phase4-base`, installs only `requirements-phase5.lock` with `--no-deps --require-hashes`, copies backend source, then returns to non-root `appuser`. It is a local cache-reuse aid, not a committed project dependency. Fresh environments use the repository's normal backend Dockerfile/Compose build and require their own dependency/acquisition budget. After explicit acquisition approval only, the pinned repository helpers are:

```powershell
docker compose exec -T backend python -m app.visual_model --root /private_data --approved-bytes 40000000
docker compose exec -T backend python -m app.visual_test_media --root /private_data --approved-bytes 20000000
```

Existing verified files are reused; mismatches fail rather than silently overwriting them. The second command retains original source files and provenance and generates the declared MP4 derivative. These are operator verification tools, not upload or inference paths.

## Responsible interpretation and limitations

These are supported-class object candidates only. They do not identify a person, connect a person across frames, predict guilt or establish that criminal activity occurred. No facial identification, person re-identification, tracking embeddings or crime classifier is implemented. Summed detections across sampled frames are not unique-object counts.

Scores are uncalibrated objectness times COCO class probability. Classes outside the model taxonomy cannot be reliably inferred. Domain shift, small/distant objects, occlusion, lighting, compression and motion blur can cause misses and false positives. Sampled-frame analysis misses events between samples and is explicitly not continuous tracking. Presentation timestamps are elapsed media time, not camera/incident wall time. Bounding-box comparisons with ONNX Runtime test implementation fidelity; they do not establish ground-truth localization accuracy, mAP, precision or recall.

Defaults bound analysis to 120 seconds, 60 samples, 2-second intervals, 8,294,400 pixels and 300 post-NMS detections/frame. Missing/non-monotonic timestamps, incomplete decoding and cap violations fail explicitly. Originals are hash-verified before processing and publication. Failed/interrupted partial artifacts stay private and cannot be exposed as complete results. Filesystem/SQL writes are separate transactions; orphan private derived bytes can remain after interruption, without automatic destructive cleanup. Retain loopback deployment and human source review.

## Approved Phase 5 pre-commit verification - 2026-10-21

The owner reviewed Phase 5 and explicitly approved its commit and normal push to the existing public GitHub repository, subject to final checks. The first approval rerun returned **82 passed, 3 failed, 0 skipped**, with **2 upstream warnings**, in **368.49 seconds**. All three JPG/JPEG/PNG failures were the same test-isolation defect: the completion-audit assertion counted every historical `visual.completed` event (3), including the two preserved demonstration jobs, instead of the event for its own new analysis (1). Earlier inference, artifact download and hash assertions passed.

The test now requires exactly one completion event scoped to its case and analysis ID, and additionally verifies its evidence ID and source SHA-256. No application code, access control, assertion threshold or existing audit record was changed. The cached image rebuild reused all dependency layers with no downloads; only backend/workers were recreated, preserving the database and volumes. A complete 85-test rerun follows this correction. Final results and staged-file checks are recorded below before the approved commit.

The corrected final complete suite passed **85 tests, 0 failed, 0 skipped**, with **2 existing upstream warnings**, in **294.08 seconds**, using:

```powershell
docker compose exec -T -e RUN_DB_TESTS=1 -e RUN_CORPUS_TESTS=1 backend python -m pytest -q -p no:cacheprovider
```

All **51 backend files** matched the tested container byte-for-byte. Alembic remains `0005_visual_analysis (head)`; pip found no broken requirements. HTTP liveness/readiness, frontend proxy, dashboard HTML and eight built assets passed. Read-only preservation verified **50 judgments, 3,834 SQL passages, 3,834 Chroma embeddings, all 57 original-file SHA-256 hashes and 20 derived hashes**. Every baseline row remains unchanged, including both existing cases and all **6 OCR/NLP runs, 16 pages and 428 entities**. The prior 55 original hashes are included in the 57 current originals. Authorized Phase 4 and Phase 5 existing-result/download checks passed without requeueing or uploading.

The reviewed commit scope is **31 paths**: source, tests, additive migration, dependency/configuration templates, documentation and the Apache-2.0 text notice. Model weights, licensed test photographs/videos, downloaded datasets, private evidence, credentials, actual `.env` files, Docker volumes, browser profiles, logs and temporary helpers remain excluded. The source secret scan and 36 ignore probes passed with no findings; static checks parsed 42 Python files and checked 32 authenticated private routes with no findings. These are custom pattern/AST/artifact checks, not a dependency-CVE or penetration-test claim. The exact staged blobs must pass the same secret/ignore checks and Git whitespace checks before committing.

Branch `main` and both origin URLs were verified as `https://github.com/yashvardhanshah/AI-Legal-Evidence-Analysis-System.git`; a normal fetch confirmed the unchanged Phase 4 base and no remote divergence. The owner explicitly approved publication to this public repository. Approved message: `feat: add computer vision evidence analysis`. Stop after the normal push and remote/hash/clean-tree confirmation; Phase 6 and UI redesign remain unauthorized.
