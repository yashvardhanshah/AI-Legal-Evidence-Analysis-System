"""Private, immutable, content-addressed originals. Never mounted as static files."""
from dataclasses import dataclass
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import tempfile

from pypdf import PdfReader


class StorageError(ValueError):
    pass


@dataclass(frozen=True)
class StoredFile:
    key: str
    sha256: str
    size: int


class PrivateStorage:
    def __init__(self, root: Path, max_bytes: int = 20_000_000):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.max_bytes = max_bytes

    def path(self, key: str) -> Path:
        if "\\" in key or ":" in key:
            raise StorageError("Unsafe storage key")
        relative = PurePosixPath(key)
        if relative.is_absolute() or not relative.parts or any(x in {"..", "."} for x in key.split("/")):
            raise StorageError("Unsafe storage key")
        path = self.root.joinpath(*relative.parts)
        if not path.resolve().is_relative_to(self.root):
            raise StorageError("Storage path escaped private root")
        current = path
        while current != self.root:
            if current.is_symlink():
                raise StorageError("Symlinks are not allowed")
            current = current.parent
        return path

    def put(self, content: bytes, namespace: str = "originals") -> StoredFile:
        if not content or len(content) > self.max_bytes:
            raise StorageError("Empty or oversized file")
        if namespace not in {"originals", "evidence-originals", "metadata", "derived"}:
            raise StorageError("Unknown storage namespace")
        digest = hashlib.sha256(content).hexdigest()
        key = f"{namespace}/{digest[:2]}/{digest}"
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise StorageError("Existing original failed integrity verification")
            return StoredFile(key, digest, len(content))
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".incoming-")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)  # Atomic create, never overwrite an original.
            except FileExistsError:
                if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise StorageError("Concurrent original failed integrity verification")
        finally:
            os.unlink(temporary)
        # Set read-only after unlinking the temporary hard link: Windows refuses
        # to unlink a read-only file, even when another hard link remains.
        os.chmod(path, 0o400)
        return StoredFile(key, digest, len(content))

    def read_verified(self, key: str, expected_sha256: str) -> bytes:
        content = self.path(key).read_bytes()
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            raise StorageError("Original failed integrity verification")
        return content


def validate_evidence(content: bytes, filename: str, max_bytes: int) -> str:
    if not content or len(content) > max_bytes:
        raise StorageError("Empty or oversized evidence")
    if Path(filename).name != filename or "/" in filename or "\\" in filename or ":" in filename or len(filename) > 255:
        raise StorageError("Unsafe original filename")
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf" and content.startswith(b"%PDF-"):
        try:
            reader = PdfReader(io.BytesIO(content), strict=True)
            if reader.is_encrypted or not reader.pages:
                raise StorageError("Encrypted or empty PDF")
        except Exception as exc:
            raise StorageError("Invalid PDF") from exc
        return "application/pdf"
    if suffix in {".jpg", ".jpeg", ".png"}:
        from PIL import Image
        expected = "PNG" if suffix == ".png" else "JPEG"
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.format != expected or image.width * image.height > 40_000_000:
                    raise StorageError("Image type or dimensions rejected")
                image.verify()
        except Exception as exc:
            raise StorageError("Invalid image") from exc
        return "image/png" if expected == "PNG" else "image/jpeg"
    if suffix == ".mp4" and len(content) >= 16 and content[4:8] == b"ftyp":
        raise StorageError("MP4 container validation is deferred to the video phase; upload is not enabled")
    raise StorageError("Unsupported evidence format or mismatched signature")
