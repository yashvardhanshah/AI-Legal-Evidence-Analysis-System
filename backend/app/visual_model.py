"""Explicit bounded acquisition and offline integrity of a publisher-pinned YOLOX model."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

MODEL = "opencv/YOLOX-S"
REVISION = "d4938dfc9d4ec5d098bfa33e98b3f3345a236586"
SOURCE_REVISION = "48b10fa505aeb51fbd127fc60a5c660040e823b7"
NAME = "object_detection_yolox_2022nov.onnx"
SIZE = 35_858_002
SHA256 = "c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063"
URL = f"https://huggingface.co/opencv/opencv_zoo/resolve/{REVISION}/models/object_detection_yolox/{NAME}"
SOURCE = f"https://github.com/opencv/opencv_zoo/tree/{SOURCE_REVISION}/models/object_detection_yolox"
CLASSES = ('person,bicycle,car,motorcycle,airplane,bus,train,truck,boat,traffic light,fire hydrant,stop sign,parking meter,bench,bird,cat,dog,horse,sheep,cow,elephant,bear,zebra,giraffe,backpack,umbrella,handbag,tie,suitcase,frisbee,skis,snowboard,sports ball,kite,baseball bat,baseball glove,skateboard,surfboard,tennis racket,bottle,wine glass,cup,fork,knife,spoon,bowl,banana,apple,sandwich,orange,broccoli,carrot,hot dog,pizza,donut,cake,chair,couch,potted plant,bed,dining table,toilet,tv,laptop,mouse,remote,keyboard,cell phone,microwave,oven,toaster,sink,refrigerator,book,clock,vase,scissors,teddy bear,hair drier,toothbrush').split(',')


class ModelUnavailable(ValueError):
    pass


def path(root):
    from app.storage import PrivateStorage
    return PrivateStorage(root).path(f"models/vision/{REVISION}/{NAME}")


def verify(root):
    target = path(root)
    try:
        if target.stat().st_size != SIZE:
            raise ValueError("Size mismatch")
        with target.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != SHA256:
                raise ValueError("Hash mismatch")
    except (OSError, ValueError) as exc:
        raise ModelUnavailable("Pinned local visual model unavailable or integrity failed") from exc
    return target


def acquire(root, approved_bytes):
    if not SIZE <= approved_bytes <= 40_000_000:
        raise ValueError("Explicit model download budget required, maximum 40 MB")
    target = path(root)
    if target.exists():
        verify(root)
        return {"bytes": SIZE, "transferred": 0, "sha256": SHA256}
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.part')
    received = 0
    with urlopen(Request(URL, headers={'User-Agent': 'AcademicEvidenceSystem/0.5'}), timeout=120) as response, temporary.open('wb') as output:
        while block := response.read(1024*1024):
            received += len(block)
            if received > SIZE or received > approved_bytes:
                raise ValueError("Approved model size exceeded")
            output.write(block)
    with temporary.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if received != SIZE or digest != SHA256:
        raise ModelUnavailable("Downloaded model does not match publisher size/hash")
    temporary.replace(target)
    target.with_suffix('.manifest.json').write_text(json.dumps(dict(model=MODEL,revision=REVISION,source=SOURCE,license='Apache-2.0',bytes=SIZE,sha256=SHA256), indent=2))
    return {"bytes": SIZE, "transferred": received, "sha256": digest}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--approved-bytes', type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(acquire(args.root, args.approved_bytes)))
