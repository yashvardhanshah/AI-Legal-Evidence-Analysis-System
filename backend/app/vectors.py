"""Explicit model acquisition, offline CPU inference and persistent cosine search."""
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

from sqlalchemy import func, or_, select

from app.config import get_settings
from app.models import Judgment, JudgmentPassage, ProcessingJob

MODEL_FILES = {"1_Pooling/config.json", "README.md", "config.json", "config_sentence_transformers.json", "model.safetensors", "modules.json", "sentence_bert_config.json", "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json", "vocab.txt"}


class VectorUnavailable(RuntimeError):
    pass


class QueryTooLong(ValueError):
    pass


def model_path() -> Path:
    settings = get_settings()
    return settings.private_root.resolve() / "models" / settings.embedding_revision


def download_model(approved_bytes: int) -> dict:
    """Operator CLI only; never invoked automatically by API or inference."""
    if not 0 < approved_bytes <= 100_000_000:
        raise ValueError("A bounded approved model budget is required")
    settings = get_settings()
    if settings.embedding_model != "sentence-transformers/all-MiniLM-L6-v2" or len(settings.embedding_revision) != 40:
        raise ValueError("Only the reviewed pinned model is supported")
    api = f"https://huggingface.co/api/models/{settings.embedding_model}/revision/{settings.embedding_revision}?blobs=true"
    with urlopen(api, timeout=60) as response:
        info = json.loads(response.read(1_000_000))
    if info["sha"] != settings.embedding_revision or info.get("cardData", {}).get("license") != "apache-2.0":
        raise ValueError("Model revision or license differs from reviewed manifest")
    files = {x["rfilename"]: x for x in info["siblings"] if x["rfilename"] in MODEL_FILES}
    if files.keys() != MODEL_FILES or sum(x["size"] for x in files.values()) > approved_bytes:
        raise ValueError("Model file manifest exceeds approval")
    directory = model_path()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    manifest = {"model": settings.embedding_model, "revision": settings.embedding_revision, "license": "Apache-2.0", "retrieved_at": datetime.now(timezone.utc).isoformat(), "files": {}}
    for name, item in sorted(files.items()):
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        expected_sha = item.get("lfs", {}).get("sha256")
        if path.exists() and path.stat().st_size == item["size"] and (not expected_sha or hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha):
            body = path.read_bytes()
        else:
            url = f"https://huggingface.co/{settings.embedding_model}/resolve/{settings.embedding_revision}/{name}"
            with urlopen(Request(url, headers={"User-Agent": "AcademicLegalEvidence/0.2"}), timeout=180) as response:
                body = response.read(item["size"] + 1)
            if len(body) != item["size"] or (expected_sha and hashlib.sha256(body).hexdigest() != expected_sha):
                raise ValueError("Model file integrity mismatch")
            temporary = path.with_suffix(path.suffix + ".part")
            temporary.write_bytes(body)
            temporary.replace(path)
        manifest["files"][name] = {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    (directory / "download-manifest.json").write_text(json.dumps(manifest, indent=2))
    return {"revision": settings.embedding_revision, "bytes": sum(x["bytes"] for x in manifest["files"].values()), "files": len(files)}


def verify_model():
    path = model_path()
    try:
        manifest = json.loads((path / "download-manifest.json").read_text())
        if manifest["revision"] != get_settings().embedding_revision or manifest["model"] != get_settings().embedding_model or manifest["license"] != "Apache-2.0" or set(manifest["files"]) != MODEL_FILES:
            raise ValueError("Model manifest mismatch")
        for name, item in manifest["files"].items():
            if hashlib.sha256((path / name).read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError("Model content mismatch")
    except (OSError, ValueError, KeyError) as exc:
        raise VectorUnavailable("Pinned model is missing or failed integrity verification") from exc


@lru_cache
def tokenizer():
    verify_model()
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(str(model_path()), local_files_only=True, trust_remote_code=False, use_fast=True)


@lru_cache
def embedder():
    verify_model()
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(2)
    model = SentenceTransformer(str(model_path()), device="cpu", local_files_only=True, trust_remote_code=False)
    model.max_seq_length = 256
    if model.get_sentence_embedding_dimension() != 384:
        raise VectorUnavailable("Unexpected embedding dimensions")
    return model


@lru_cache
def collection():
    import chromadb
    from chromadb.config import Settings
    settings = get_settings()
    client = chromadb.PersistentClient(path=str(settings.private_root.resolve() / "chroma"), settings=Settings(anonymized_telemetry=False, allow_reset=False))
    result = client.get_or_create_collection(name=settings.chroma_collection, embedding_function=None,
        metadata={"hnsw:space": "cosine", "model": settings.embedding_model, "revision": settings.embedding_revision})
    if result.metadata.get("revision") != settings.embedding_revision or result.metadata.get("model") != settings.embedding_model or result.metadata.get("hnsw:space") != "cosine":
        raise VectorUnavailable("Collection model or distance metric mismatch")
    return result


def index_passages(session) -> dict:
    settings = get_settings()
    job = ProcessingJob(kind="embedding_index", status="processing", attempts=1, total=0, processed=0,
                        started_at=datetime.now(timezone.utc), details={"model": settings.embedding_model, "revision": settings.embedding_revision})
    session.add(job)
    session.commit()
    try:
        ids = list(session.scalars(select(JudgmentPassage.id).where(or_(JudgmentPassage.vector_id.is_(None), JudgmentPassage.embedding_revision.is_(None), JudgmentPassage.embedding_revision != settings.embedding_revision)).order_by(JudgmentPassage.id)))
        job.total = len(ids)
        session.commit()
        for start in range(0, len(ids), 64):
            rows = list(session.scalars(select(JudgmentPassage).where(JudgmentPassage.id.in_(ids[start:start+64])).order_by(JudgmentPassage.id)))
            vectors = embedder().encode([row.text for row in rows], batch_size=32, normalize_embeddings=True, show_progress_bar=False)
            vector_ids = [str(row.id) for row in rows]
            collection().upsert(ids=vector_ids, embeddings=vectors.tolist(), metadatas=[{"judgment_id": str(row.judgment_id), "text_sha256": row.text_sha256} for row in rows])
            for row in rows:
                row.vector_id = str(row.id)
                row.embedding_revision = settings.embedding_revision
                row.indexed_at = datetime.now(timezone.utc)
            job.processed += len(rows)
            session.commit()
        job.status = "completed"
        job.finished_at = datetime.now(timezone.utc)
        session.commit()
        return {"job_id": str(job.id), "newly_indexed": len(ids), "collection_count": collection().count()}
    except Exception as exc:
        session.rollback()
        job = session.get(ProcessingJob, job.id)
        job.status, job.error_code, job.finished_at = "failed", type(exc).__name__[:100], datetime.now(timezone.utc)
        session.commit()
        raise


def semantic_search(session, query: str, limit: int = 5) -> list[dict]:
    settings = get_settings()
    store = collection()
    if not store.count():
        if session.scalar(select(func.count()).select_from(JudgmentPassage)):
            raise VectorUnavailable("Corpus passages exist but are not indexed yet")
        return []
    if len(tokenizer().encode(query, add_special_tokens=True, truncation=False)) > 256:
        raise QueryTooLong("Query exceeds the 256-token model context; shorten the query")
    vector = embedder().encode([query], normalize_embeddings=True, show_progress_bar=False).tolist()
    matches = store.query(query_embeddings=vector, n_results=min(store.count(), max(100, limit * 20)), include=["distances", "metadatas"])
    # Fetch provenance in one bounded SQL query, then preserve vector rank while
    # choosing the best matching passage from each distinct judgment.
    rows = session.execute(select(JudgmentPassage, Judgment).join(Judgment, Judgment.id == JudgmentPassage.judgment_id).where(
        JudgmentPassage.vector_id.in_(matches["ids"][0]), JudgmentPassage.embedding_revision == settings.embedding_revision))
    by_vector = {passage.vector_id: (passage, judgment) for passage, judgment in rows}
    output, seen = [], set()
    for vector_id, distance, metadata in zip(matches["ids"][0], matches["distances"][0], matches["metadatas"][0]):
        row = by_vector.get(vector_id)
        if not row:
            continue  # Never return orphaned/uncommitted vectors as source records.
        passage, judgment = row
        if metadata.get("text_sha256") != passage.text_sha256 or judgment.id in seen:
            continue
        seen.add(judgment.id)
        output.append({"judgment_id": str(judgment.id), "passage_id": str(passage.id), "title": judgment.title, "court": judgment.court,
                       "judgment_date": judgment.judgment_date.isoformat() if judgment.judgment_date else None, "citation": judgment.citation,
                       "source_url": judgment.source_url, "excerpt": passage.text, "page_number": passage.page_number,
                       "distance": float(distance), "metric": "cosine_distance", "model_revision": settings.embedding_revision})
        if len(output) == limit:
            break
    return output
