"""Pinned, explicitly approved NER acquisition; inference never downloads files."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

MODEL = "dslim/distilbert-NER"
REVISION = "dfa2838a127384aabb82ed7719e16dab84c42a2a"
WEIGHTS_SHA256 = "235ecd699f650ca36513b122d11ce5a80339be1388f06c33c2278368b99914e1"
FILES = {"README.md": 6170, "config.json": 926, "model.safetensors": 260803668,
         "special_tokens_map.json": 125, "tokenizer.json": 669021, "tokenizer_config.json": 1197, "vocab.txt": 213450}
TOTAL_BYTES = sum(FILES.values())


class ModelUnavailable(ValueError):
    pass


def directory(root):
    from app.storage import PrivateStorage
    return PrivateStorage(root).path(f"models/ner/{REVISION}")


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(root, approved_bytes):
    if not TOTAL_BYTES <= approved_bytes <= 300_000_000:
        raise ValueError("Explicit approved budget between pinned size and 300 MB required")
    api = f"https://huggingface.co/api/models/{MODEL}/revision/{REVISION}?blobs=true"
    with urlopen(Request(api, headers={"User-Agent": "AcademicEvidenceSystem/0.4"}), timeout=60) as response:
        metadata = json.load(response)
    entries = {item["rfilename"]: item for item in metadata["siblings"] if item["rfilename"] in FILES}
    if metadata["sha"] != REVISION or metadata.get("cardData", {}).get("license") != "apache-2.0" or {name: item["size"] for name, item in entries.items()} != FILES:
        raise ValueError("Publisher manifest differs from reviewed model")
    if entries["model.safetensors"].get("lfs", {}).get("sha256") != WEIGHTS_SHA256:
        raise ValueError("Publisher weights hash differs from reviewed model")
    folder = directory(root)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = {"model": MODEL, "revision": REVISION, "license": "Apache-2.0", "files": {}}
    transferred = 0
    for name, size in FILES.items():
        path = folder/name
        if not path.exists():
            temporary = folder/(name+".part")
            received = 0
            with urlopen(Request(f"https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}", headers={"User-Agent": "AcademicEvidenceSystem/0.4"}), timeout=120) as response, temporary.open("wb") as output:
                while block := response.read(1024*1024):
                    received += len(block)
                    transferred += len(block)
                    if received > size or transferred > approved_bytes:
                        raise ValueError("Approved download budget exceeded")
                    output.write(block)
            if received != size:
                raise ValueError("Incomplete model file")
            if name == "model.safetensors" and file_hash(temporary) != WEIGHTS_SHA256:
                raise ValueError("Downloaded weights failed publisher hash")
            temporary.replace(path)
        if path.stat().st_size != size:
            raise ValueError("Existing model file size mismatch; do not overwrite silently")
        sha = file_hash(path)
        if name == "model.safetensors" and sha != WEIGHTS_SHA256:
            raise ValueError("Model weights integrity mismatch")
        receipt["files"][name] = {"bytes": size, "sha256": sha}
    (folder/"download-manifest.json").write_text(json.dumps(receipt, indent=2))
    return {"model": MODEL, "revision": REVISION, "bytes": TOTAL_BYTES, "transferred_bytes": transferred, "files": len(FILES)}


def verify(root):
    folder = directory(root)
    try:
        receipt = json.loads((folder/"download-manifest.json").read_text())
        if receipt["model"] != MODEL or receipt["revision"] != REVISION or receipt["license"] != "Apache-2.0" or set(receipt["files"]) != set(FILES):
            raise ValueError("Manifest mismatch")
        for name, size in FILES.items():
            item = receipt["files"][name]
            if item["bytes"] != size or (folder/name).stat().st_size != size or file_hash(folder/name) != item["sha256"]:
                raise ValueError("Model file integrity mismatch")
        if receipt["files"]["model.safetensors"]["sha256"] != WEIGHTS_SHA256:
            raise ValueError("Weights mismatch")
    except (OSError, KeyError, ValueError) as exc:
        raise ModelUnavailable("Approved pinned NER model is unavailable or failed verification") from exc
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--approved-bytes", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(download(args.root, args.approved_bytes), indent=2))
