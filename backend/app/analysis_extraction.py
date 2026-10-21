"""Page-level embedded text or real Tesseract TSV, separate from originals."""
import csv
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageOps
from pypdf import PdfReader


class AnalysisFailure(ValueError):
    def __init__(self, code, retryable=False):
        super().__init__(code)
        self.code, self.retryable = code, retryable


def canonical(text):
    # PostgreSQL cannot store NUL. Do not silently normalize words or punctuation.
    return text.replace("\x00", "\ufffd").replace("\r\n", "\n").replace("\r", "\n")


def parse_tsv(tsv):
    text, words, prior_line = "", [], None
    try:
        for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
            if row.get("level") != "5" or not (row.get("text") or "").strip():
                continue
            word = canonical(row["text"])
            line = tuple(row[k] for k in ("block_num", "par_num", "line_num"))
            if words:
                text += "\n" if prior_line != line else " "
            start = len(text)
            text += word
            confidence = float(row["conf"])
            words.append({"text": word, "char_start": start, "char_end": len(text),
                          "confidence": confidence if 0 <= confidence <= 100 else None,
                          "box": {key: int(row[key]) for key in ("left", "top", "width", "height")}})
            prior_line = line
    except (KeyError, ValueError, TypeError) as exc:
        raise AnalysisFailure("ocr_output_invalid") from exc
    scored = [word for word in words if word["confidence"] is not None]
    confidence = sum(w["confidence"]*len(w["text"]) for w in scored)/sum(len(w["text"]) for w in scored) if scored else None
    return text, words, confidence


def ocr(image, settings):
    if image.width*image.height > settings.analysis_max_pixels:
        raise AnalysisFailure("render_limit_exceeded")
    with tempfile.TemporaryDirectory(prefix="legal-ocr-") as folder:
        path = Path(folder)/"page.png"
        image.save(path, format="PNG")
        try:
            result = subprocess.run(["tesseract", str(path), "stdout", "-l", "eng", "--psm", "3", "tsv"],
                                    capture_output=True, timeout=settings.analysis_ocr_timeout, check=True,
                                    env={**os.environ, "OMP_THREAD_LIMIT": "1"})
        except subprocess.TimeoutExpired as exc:
            raise AnalysisFailure("ocr_timeout", True) from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise AnalysisFailure("ocr_failed", True) from exc
    text, words, confidence = parse_tsv(result.stdout.decode("utf-8", errors="strict"))
    return {"text": text, "ocr_words": words, "ocr_confidence": confidence,
            "width": image.width, "height": image.height, "warnings": [] if text.strip() else ["no_text_on_page"]}


def pdf_reader(content, settings):
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted or not reader.pages:
            raise AnalysisFailure("invalid_document")
        if len(reader.pages) > settings.analysis_max_pages:
            raise AnalysisFailure("page_limit_exceeded")
        return reader
    except AnalysisFailure:
        raise
    except Exception as exc:
        raise AnalysisFailure("invalid_document") from exc


def page_count(content, mime, settings):
    if mime == "application/pdf":
        return len(pdf_reader(content, settings).pages)
    if mime in {"image/png", "image/jpeg"}:
        return 1
    raise AnalysisFailure("unsupported_document")


def extract_pages(content, mime, settings):
    total_chars = 0
    document = None
    try:
        if mime == "application/pdf":
            reader = pdf_reader(content, settings)
            for number, page in enumerate(reader.pages, 1):
                try:
                    text = canonical(page.extract_text() or "")
                except Exception as exc:
                    raise AnalysisFailure("pdf_text_extraction_failed") from exc
                # A short or missing text layer gets a genuine OCR attempt.
                if sum(c.isalnum() for c in text) >= 24:
                    result = {"text": text, "extraction_method": "pypdf-embedded", "ocr_words": [],
                              "ocr_confidence": None, "width": None, "height": None, "warnings": []}
                else:
                    import pypdfium2 as pdfium
                    if document is None:
                        document = pdfium.PdfDocument(content)
                    pdfpage = document[number-1]
                    try:
                        width, height = pdfpage.get_size()
                        scale = min(settings.analysis_render_dpi/72, (settings.analysis_max_pixels/max(width*height, 1))**0.5*0.99)
                        bitmap = pdfpage.render(scale=scale)
                        try:
                            image = bitmap.to_pil().convert("RGB")
                        finally:
                            bitmap.close()
                    finally:
                        pdfpage.close()
                    result = {**ocr(image, settings), "extraction_method": "tesseract-pdf-eng"}
                    image.close()
                total_chars += len(result["text"])
                validate_size(result, total_chars, settings)
                yield {"page_number": number, "text_sha256": hashlib.sha256(result["text"].encode()).hexdigest(), **result}
        elif mime in {"image/png", "image/jpeg"}:
            try:
                with Image.open(io.BytesIO(content)) as original:
                    if original.width*original.height > settings.analysis_max_pixels:
                        raise AnalysisFailure("render_limit_exceeded")
                    image = ImageOps.exif_transpose(original).convert("RGB")
                    result = {**ocr(image, settings), "extraction_method": "tesseract-image-eng"}
                    image.close()
            except AnalysisFailure:
                raise
            except Exception as exc:
                raise AnalysisFailure("invalid_document") from exc
            validate_size(result, len(result["text"]), settings)
            yield {"page_number": 1, "text_sha256": hashlib.sha256(result["text"].encode()).hexdigest(), **result}
        else:
            raise AnalysisFailure("unsupported_document")
    finally:
        if document:
            document.close()


def validate_size(page, total_chars, settings):
    if len(page["text"]) > settings.analysis_max_page_chars or total_chars > settings.analysis_max_chars:
        raise AnalysisFailure("text_limit_exceeded")
