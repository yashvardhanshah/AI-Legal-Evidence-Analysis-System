# Phase 5 implementation plan

Extend the existing PostgreSQL jobs, private immutable storage, case authorization and subprocess worker. Preserve Phase 4's default worker behavior and all existing records. No tracking, facial identification, person re-identification, crime inference or legal conclusions.

1. Review/pin the Apache-2.0 OpenCV Zoo YOLOX-S ONNX snapshot, official preprocessing/postprocessing, wheel compatibility and authentic test media licenses. Acquire only after bounded download approval. Keep all model/media files ignored.
2. Add migration 0005 with visual analyses, frames and detections; reuse existing job, model registry and immutable artifact tables. Keep restrictive foreign keys, attempt history and one-active-visual-job-per-evidence uniqueness.
3. Add CPU OpenCV DNN inference: RGB 0–255, top-left 640-square letterbox with 114 padding, anchor-free grid decoding, confidence = objectness times maximum class probability, per-class NMS. Report only actual supported COCO class names. Preserve dimensions, exact decoded pixel hashes, source SHA-256 and model provenance.
4. Decode MP4 locally using OpenCV FFmpeg with external references/protocols disabled; sequential frame indices and actual presentation timestamps. Sample first frame and then at configured elapsed-time intervals. Reject missing/non-monotonic timestamps and configured duration/pixel/frame limits explicitly. No continuous tracking or implied completeness between samples.
5. Extend fenced SQL worker dispatch, current-access checks, bounded retries and deadlines; add an isolated visual-worker service with read-only source/model mounts and private derived output. Upload/API handlers only enqueue.
6. Add scoped trigger/history/retry/results/frame/artifact endpoints and minimal case-page controls. Artifact access must authenticate, recheck case/evidence/run relationships, require completed results and verify hashes; never expose private filesystem paths.
7. Test actual model output against the existing independent ONNX Runtime, bounds/timestamps, authorization, deduplication, failures/retries/fencing, audit records and restart persistence. Run every Phase 1–4 regression and record exact results, measured timings and observed candidates in PHASE5_REPORT.md and TESTING.md.

## Reviewed acquisition metadata

OpenCV Zoo source revision: `48b10fa505aeb51fbd127fc60a5c660040e823b7`. Publisher states all files in `models/object_detection_yolox` are Apache-2.0. Model is YOLOX-S with 80 COCO categories, not a face/person identity model. Official model source: https://github.com/opencv/opencv_zoo/tree/48b10fa505aeb51fbd127fc60a5c660040e823b7/models/object_detection_yolox .

Model mirror revision: `d4938dfc9d4ec5d098bfa33e98b3f3345a236586` at https://huggingface.co/opencv/opencv_zoo . File `models/object_detection_yolox/object_detection_yolox_2022nov.onnx`: 35,858,002 bytes; publisher LFS SHA-256 `c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063`. The downloaded bytes must match both exact size and hash. No Torch pickle or executable remote model code.

OpenCV headless CPU wheel: `opencv-python-headless==5.0.0.93`, Apache-2.0 distribution; requires NumPy >=2 on Python >=3.9, compatible with the installed NumPy 2.5.4. Linux x86_64 wheel sizes: 61,204,038 bytes (manylinux_2_28), or 56,563,598 bytes (manylinux2014). Existing ONNX Runtime 1.31.0 is reused for independent verification. No Torch/Transformers/Chroma replacement.

Proposed genuine test files: original https://commons.wikimedia.org/wiki/File:YellowLabradorLooking.jpg (Elf photograph, color revision by Carla Nunziata, CC BY-SA 3.0, 700x577, about 137 KB; avoid the separate owner-removed retouched derivative); https://commons.wikimedia.org/wiki/File:Jijiga.ogv (Brian Dell, own traffic footage, CC0 1.0, 12 seconds, 1920x1080, about 17.37 MB). Preserve fetched originals and receipts; explicitly label the local MP4 transcode as a derivative, not a camera-original MP4. Annotated photographs retain CC BY-SA attribution/derivative terms when shared. No test media is committed.

The owner approved those bounded acquisitions. Verified downloaded source SHA-256: photo `ea1daaac9860befcbeb11b65c2d7da2a71c74d06c345dbc205f0b41797023425` (140,606 bytes), traffic OGV `2c75b1ae879ebfadb7473d24e29b34c072430cabe8f0b5e5e68f68e58ab372d2` (18,214,298 bytes). Declared full-footage H.264/960-wide/no-audio MP4 derivative: `286fe2b29d13f9b174dcdc665f734ee64de9cdbe82010e7bb8f8972c00b6b80f` (2,563,991 bytes). Sources and attribution receipts remain under ignored private storage. The ONNX bytes matched the publisher hash and size above. The owner approved a revised 250-MB total network cap after an unexpected base-layer refresh. The pinned OpenCV wheel is installed using the existing Phase 4 image; no ML dependency replacement or repeat model download occurred. Full verification results are recorded in PHASE5_REPORT.md.

## API and access policy

Every route below has prefix `/api/v1/cases/{case_id}/evidence/{evidence_id}`. Current authentication and case/evidence access are required on every request. Case owner/admin or assigned investigator/lawyer may trigger/retry active-case work; assigned researchers may read complete results. Mutations retain CSRF/origin checks and row locks. Inaccessible identifiers return generic 404; unauthenticated requests return 401. No private visual job appears in public corpus job APIs.

| Method and suffix | Purpose |
| --- | --- |
| POST /visual-analysis | Queue/reuse active work (202); reuse matching completed result (200); `{reanalyze:true}` creates a new version |
| GET /visual-jobs | Scoped paginated status/progress/attempt history |
| GET /visual-jobs/{job_id} | Scoped sanitized job and retained run metadata |
| POST /visual-jobs/{job_id}/retry | Retry failed attempts below the cap, rechecking queue and case permissions |
| GET /visual-analyses | Scoped paginated version history |
| GET /visual-analyses/{analysis_id} | Source/model/settings/media metadata and audited read |
| GET /visual-analyses/{analysis_id}/frames | Completed sampled frames and detections, paginated and audited |
| GET /visual-analyses/{analysis_id}/frames/{frame_id}/artifact | Authenticated, completed-run, hash-verified PNG; `annotated=false` returns the unannotated decoded source derivative |

Partial/failed/interrupted run artifacts return 409; wrong evidence/run/frame relationships return 404. Responses never include private storage paths or lease tokens. Artifact responses have no-store, nosniff and SHA-256 headers; the browser verifies fetched hashes before creating private blob URLs and revokes them on navigation. All media/text/class labels render as escaped content.

## Limits, coordinates and interpretation

Defaults: confidence 0.35, class-aware NMS IoU 0.5, 640x640 model input, 2-second elapsed-time sampling, 60 sampled frames, 120 seconds and 8,294,400 decoded pixels. Up to 300 post-NMS detections per sample; exceeding a cap fails explicitly rather than silently truncating. Uploaded MP4s retain the earlier signature/codec/complete-decode validation and 20-MB file cap. Visual analysis can apply stricter duration limits than upload validation.

OpenCV sequentially decodes every video frame, retaining the first frame and the first available presentation frame at/after each interval. Video timestamps come from FFmpeg-backed CAP_PROP_POS_MSEC after read, cross-checked in tests against ffprobe. No timestamps are synthesized from frame index/fps when actual timestamps are unavailable. Non-monotonic/missing timing, incomplete decode and oversized media fail explicitly. Timestamps are elapsed media presentation time, not incident/camera wall time. Progress while decoding uses the bounded sample budget; completion records the actual total sample count.

Bounding boxes use continuous `x1,y1,x2,y2` coordinates within the decoded orientation-adjusted source dimensions, clipped to source bounds after reversing the letterbox scale. Raw output index, letterbox ratio, pre-clipped model-space box, objectness, class probability and raw output hash provide provenance. Source derivative BGR pixel hashes are separate from original encoded-file SHA-256. EXIF/rotation adjustments apply to derivatives only; original encoded dimensions remain in media metadata. Zero detections is a valid completed result, not fabricated success with invented objects.

Candidate scores are objectness times maximum COCO class probability and are uncalibrated. Repeated detections across frames are not unique-person/vehicle counts or trajectories. No facial identity, re-identification embeddings, person matching, guilt prediction or activity/crime classifier is implemented. Sampling misses events between frames. Occlusion, small/distant objects, motion blur, domain shift and unsupported COCO classes limit recall and localization. Reference-runtime agreement tests implementation fidelity, not ground-truth real-world accuracy or legal reliability.

## Storage, workers and preservation

Revision `0005_visual_analysis` adds `visual_analyses`, `visual_frames`, `visual_detections` and a partial unique active-visual-job/evidence index. Existing generic processing jobs, model registry and immutable artifact records are reused. No old fields or rows are rewritten. A private baseline holds SHA-256 fingerprints of all pre-existing corpus/case/evidence/artifact/model/OCR run/page/entity/job records; post-run checks must confirm each original row unchanged, original-file hashes intact and the Chroma collection still at 3,834.

The existing worker's default document path is preserved; `--kind visual_analysis` selects visual attempts and a separate heartbeat. Both use session advisory locks, SKIP LOCKED, bounded attempts, lease UUID fencing, child process-group timeouts, current case authorization checks before/after inference and publication, and immutable failed/interrupted histories. A stale worker cannot publish over a new lease. Failed partial artifacts remain private and cannot be read as completed analyses. Filesystem and SQL writes are separate transactions, so unreferenced private derived files can remain after interruption; no automatic deletion or destructive cleanup is performed.

The visual-worker has no published port, runs as non-root, limits CPU/memory/processes and mounts only originals/model weights read-only plus private derived storage writable. It does not mount authentication credentials, public judgment PDFs, Chroma or test-media acquisition receipts. Inference never fetches files or calls external APIs. Format parsing is bounded, and local FFmpeg/OpenCV disable external protocols/container references; parser/model vulnerabilities are still a reason to retain loopback deployment. No production hardening or public deployment is claimed in this phase.
