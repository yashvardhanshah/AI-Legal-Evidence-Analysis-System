"""PDF extraction and tokenizer-aware page chunks, without modifying originals."""
import hashlib
import io
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

from pypdf import PdfReader


class ExtractionError(ValueError):
    pass


class OCRRequired(ExtractionError):
    pass


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\x00", "")
    return re.sub(r"\s+", " ", text).strip()


def extract_pdf(content: bytes, max_pages: int, allow_ocr=False, ocr_timeout=60) -> tuple[list[str], str]:
    if not content.startswith(b"%PDF-"):
        raise ExtractionError("Invalid PDF signature")
    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted or not 0 < len(reader.pages) <= max_pages:
        raise ExtractionError("Encrypted, empty or oversized page count")
    pages, used_ocr = [], False
    for number, page in enumerate(reader.pages):
        text = clean_text(page.extract_text() or "")
        resources = page.get("/Resources", {})
        if hasattr(resources, "get_object"):
            resources = resources.get_object()
        if not text and resources.get("/XObject"):
            if not allow_ocr:
                raise OCRRequired(f"Page {number + 1} requires OCR")
            import pypdfium2 as pdfium
            document = pdfium.PdfDocument(content)
            try:
                image = document[number].render(scale=2).to_pil()
                with tempfile.TemporaryDirectory() as temporary:
                    image_path = Path(temporary) / "page.png"
                    image.save(image_path)
                    result = subprocess.run(["tesseract", str(image_path), "stdout", "-l", "eng"], capture_output=True, timeout=ocr_timeout, check=True)
                    text = clean_text(result.stdout.decode("utf-8"))
            finally:
                document.close()
            used_ocr = True
            if not text:
                raise ExtractionError(f"OCR produced no text on page {number + 1}")
        pages.append(text)
    if sum(len(page) for page in pages) < 30:
        raise ExtractionError("Document contains insufficient extractable text")
    return pages, "pypdf+tesseract-eng" if used_ocr else "pypdf-embedded"


def chunk_pages(pages: list[str], tokenizer, window=220, overlap=32) -> list[dict]:
    if not 0 <= overlap < window <= 254:
        raise ValueError("Invalid tokenizer window")
    passages = []
    for number, text in enumerate(pages, start=1):
        encoded = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True, truncation=False, verbose=False)
        offsets = encoded["offset_mapping"]
        start = 0
        while start < len(offsets):
            end = min(start + window, len(offsets))
            first, last = offsets[start][0], offsets[end - 1][1]
            excerpt = text[first:last]
            token_count = len(tokenizer.encode(excerpt, add_special_tokens=True, truncation=False))
            if token_count > 256:
                raise ValueError("Chunk exceeds model context; no silent truncation allowed")
            if excerpt.strip():
                passages.append(dict(ordinal=len(passages), page_number=number, char_start=first, char_end=last, token_count=token_count, text=excerpt, text_sha256=hashlib.sha256(excerpt.encode()).hexdigest()))
            if end == len(offsets):
                break
            start = end - overlap
    return passages
