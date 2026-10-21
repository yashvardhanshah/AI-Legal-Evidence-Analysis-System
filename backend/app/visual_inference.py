"""Real offline YOLOX/OpenCV: bounded decoding, timestamped samples and pixel-space boxes.

YOLOX preprocessing/grid conventions adapted from the Apache-2.0 OpenCV Zoo
reference at revision 48b10fa505aeb51fbd127fc60a5c660040e823b7.
Copyright (c) 2021-2022 Megvii Inc.; retained license: docs/licenses/YOLOX-APACHE-2.0.md.
Modified here for source-coordinate provenance, integrity and bounded private jobs.
"""
from functools import lru_cache
import hashlib
import io
import math
import os
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageOps

from app.config import get_settings
from app import visual_model


class VisualFailure(ValueError):
    def __init__(self, code, retryable=False):
        super().__init__(code)
        self.code, self.retryable = code, retryable


def cv():
    # Disable external stream references even for preserved local container files.
    os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'protocol_whitelist;file|enable_drefs;0|use_absolute_path;0|threads;1'
    import cv2
    cv2.setNumThreads(2)
    return cv2


def prepare(image):
    import numpy as np
    cv2 = cv()
    h, w = image.shape[:2]
    ratio = min(640/w, 640/h)
    resized = cv2.resize(image, (int(w*ratio), int(h*ratio)), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((640, 640, 3), 114, dtype=np.uint8)
    canvas[:resized.shape[0], :resized.shape[1]] = resized
    # Publisher demo uses RGB pixels without scaling/mean normalization.
    return np.ascontiguousarray(canvas[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32), ratio


@lru_cache
def net():
    cv2 = cv()
    model = cv2.dnn.readNetFromONNX(str(visual_model.verify(get_settings().private_root)))
    model.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    model.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    return model


def decode(output, ratio, width, height, confidence, nms):
    import numpy as np
    cv2 = cv()
    if output.shape != (1, 8400, 85) or not np.isfinite(output).all():
        raise VisualFailure('model_output_invalid')
    values = output[0].copy()
    grids, strides = [], []
    for stride in (8, 16, 32):
        x, y = np.meshgrid(np.arange(640//stride), np.arange(640//stride))
        grids.append(np.stack((x, y), axis=-1).reshape(-1, 2))
        strides.append(np.full((x.size, 1), stride))
    grid, stride = np.concatenate(grids), np.concatenate(strides)
    centers = (values[:, :2]+grid)*stride
    with np.errstate(over='raise', invalid='raise'):
        try:
            sizes = np.exp(values[:, 2:4])*stride
        except FloatingPointError as exc:
            raise VisualFailure('model_output_invalid') from exc
    boxes = np.concatenate((centers-sizes/2, sizes), axis=1)
    scores = values[:, 4:5]*values[:, 5:]
    labels = scores.argmax(axis=1)
    maxima = scores.max(axis=1)
    keep = cv2.dnn.NMSBoxesBatched(boxes.tolist(), maxima.tolist(), labels.tolist(), confidence, nms)
    if len(keep) > 300:
        raise VisualFailure('detection_limit_exceeded')
    results = []
    output_digest = hashlib.sha256(output.tobytes()).hexdigest()
    for index in np.asarray(keep).reshape(-1).tolist():
        x, y, w, h = (boxes[index]/ratio).tolist()
        x1, y1, x2, y2 = max(0., min(width, x)), max(0., min(height, y)), max(0., min(width, x+w)), max(0., min(height, y+h))
        if x2 <= x1 or y2 <= y1:
            continue  # Padding-only proposal, outside source pixels.
        label = int(labels[index])
        score = float(maxima[index])
        if not 0 <= score <= 1:
            raise VisualFailure('model_output_invalid')
        results.append(dict(class_id=label, label=visual_model.CLASSES[label], confidence=score,
            x1=x1, y1=y1, x2=x2, y2=y2,
            provenance=dict(output_index=index, objectness=float(values[index,4]),
                class_probability=float(values[index,5+label]), raw_xywh=boxes[index].tolist(), letterbox_ratio=ratio,
                coordinate_system='decoded orientation-adjusted source pixels; xyxy, continuous end coordinates',
                score_method='objectness times maximum COCO class probability; uncalibrated',
                raw_output_sha256=output_digest)))
    return results


def detect(image):
    blob, ratio = prepare(image)
    model = net()
    start = time.perf_counter()
    model.setInput(blob)
    output = model.forward()
    elapsed = (time.perf_counter()-start)*1000
    h, w = image.shape[:2]
    settings = get_settings()
    return decode(output, ratio, w, h, settings.visual_confidence, settings.visual_nms), elapsed


def png(image):
    good, encoded = cv().imencode('.png', image)
    if not good:
        raise VisualFailure('artifact_failed', True)
    return encoded.tobytes()


def annotate(image, detections):
    cv2 = cv()
    result = image.copy()
    for item in detections:
        x1, y1, x2, y2 = [int(round(item[key])) for key in ('x1','y1','x2','y2')]
        cv2.rectangle(result, (x1,y1), (x2,y2), (0,180,255), 2)
        cv2.putText(result, f"{item['label']} {item['confidence']:.3f}", (x1,max(15,y1-5)), cv2.FONT_HERSHEY_SIMPLEX, .55, (0,180,255), 2)
    return result


def check_pixels(width, height):
    if not 0 < width*height <= get_settings().visual_max_pixels:
        raise VisualFailure('pixel_limit_exceeded')


def frames(raw, mime):
    import numpy as np
    settings, cv2 = get_settings(), cv()
    if mime in {'image/png','image/jpeg'}:
        try:
            with Image.open(io.BytesIO(raw)) as original:
                check_pixels(*original.size)
                source_size = original.size
                oriented = ImageOps.exif_transpose(original).convert('RGB')
                image = cv2.cvtColor(np.asarray(oriented), cv2.COLOR_RGB2BGR)
                oriented.close()
            yield dict(frame_index=0, timestamp_ms=0., image=image,
                media=dict(kind='image', original_width=source_size[0],original_height=source_size[1],
                           orientation='EXIF transpose on derivative only',timestamp_basis='single image, no capture time inferred'), total=1)
        except VisualFailure:
            raise
        except Exception as exc:
            raise VisualFailure('invalid_media') from exc
        return
    if mime != 'video/mp4':
        raise VisualFailure('unsupported_visual')
    from app.storage import validate_mp4, StorageError
    try:
        validate_mp4(raw)  # Bounded signature/container/decode validation with external references disabled.
    except StorageError as exc:
        raise VisualFailure('invalid_media') from exc
    with tempfile.TemporaryDirectory(prefix='legal-visual-') as folder:
        target = Path(folder)/'source.mp4'
        target.write_bytes(raw)
        capture = cv2.VideoCapture(str(target), cv2.CAP_FFMPEG)
        try:
            if not capture.isOpened():
                raise VisualFailure('invalid_media')
            # Normalize rotation explicitly on each derivative, preserving original encoded dimensions.
            capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 0)
            rotation = int(capture.get(cv2.CAP_PROP_ORIENTATION_META))
            width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps, count = capture.get(cv2.CAP_PROP_FPS), int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            check_pixels(width, height)
            if not math.isfinite(fps) or not 0 < fps <= 120 or count <= 0:
                raise VisualFailure('invalid_timestamps')
            duration = count/fps
            if duration > settings.visual_max_seconds or count > settings.visual_max_seconds*120:
                raise VisualFailure('duration_limit_exceeded')
            if math.ceil(duration*1000/settings.visual_interval_ms) > settings.visual_max_frames:
                raise VisualFailure('frame_limit_exceeded')
            media = dict(kind='video', original_width=width,original_height=height, fps=fps, frame_count=count,
                duration_seconds=duration, rotation_degrees=rotation, interval_ms=settings.visual_interval_ms,
                sampling='first frame then first actual presentation timestamp at or after each elapsed interval; sequential decode; no tracking',
                timestamp_basis='OpenCV FFmpeg CAP_PROP_POS_MSEC after read; elapsed presentation time, not camera wall time')
            index, sampled, previous, next_sample, first = 0, 0, -1., 0., None
            while True:
                ok, image = capture.read()
                if not ok:
                    break
                stamp = float(capture.get(cv2.CAP_PROP_POS_MSEC))
                if not math.isfinite(stamp) or stamp < 0 or (index and stamp <= previous):
                    raise VisualFailure('invalid_timestamps')
                if abs(capture.get(cv2.CAP_PROP_POS_FRAMES)-(index+1)) > .1:
                    raise VisualFailure('invalid_timestamps')
                previous = stamp
                if first is None:
                    first = stamp
                if stamp-first > settings.visual_max_seconds*1000:
                    raise VisualFailure('duration_limit_exceeded')
                if stamp-first+1e-5 >= next_sample:
                    sampled += 1
                    if sampled > settings.visual_max_frames:
                        raise VisualFailure('frame_limit_exceeded')
                    if rotation == 90: image = cv2.rotate(image,cv2.ROTATE_90_CLOCKWISE)
                    elif rotation == 180: image = cv2.rotate(image,cv2.ROTATE_180)
                    elif rotation == 270: image = cv2.rotate(image,cv2.ROTATE_90_COUNTERCLOCKWISE)
                    elif rotation != 0: raise VisualFailure('invalid_media')
                    yield dict(frame_index=index,timestamp_ms=stamp,image=image,media=media,total=settings.visual_max_frames)
                    next_sample = (math.floor((stamp-first)/settings.visual_interval_ms)+1)*settings.visual_interval_ms
                index += 1
            if not sampled or index != count:
                raise VisualFailure('decode_incomplete')
        finally:
            capture.release()
