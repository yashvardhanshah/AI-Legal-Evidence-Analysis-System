"""Bounded operator commands; no network writes or ingestion exposed through HTTP."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.database import get_engine


@contextmanager
def writer_session():
    with get_engine().connect().execution_options(isolation_level="AUTOCOMMIT") as lock:
        if not lock.scalar(text("SELECT pg_try_advisory_lock(260219, 2)")):
            raise RuntimeError("Another corpus writer is running; retry after it finishes")
        try:
            with Session(get_engine()) as session:
                yield session
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(260219, 2)"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("register-sources")
    model = commands.add_parser("download-model")
    model.add_argument("--approved-bytes", type=int, required=True)
    plan = commands.add_parser("plan-supreme")
    plan.add_argument("--year", type=int, required=True)
    plan.add_argument("--limit", type=int, default=50)
    plan.add_argument("--output", type=Path, required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("--manifest", type=Path, required=True)
    ingest.add_argument("--approved-sha256", required=True)
    ingest.add_argument("--max-total-bytes", type=int, required=True)
    ingest.add_argument("--retry-job", type=UUID)
    acquire = commands.add_parser("acquire")
    acquire.add_argument("--manifest", type=Path, required=True)
    acquire.add_argument("--approved-sha256", required=True)
    acquire.add_argument("--max-total-bytes", type=int, required=True)
    commands.add_parser("index")
    search = commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=5, choices=range(1, 21))
    evidence = commands.add_parser("import-evidence")
    evidence.add_argument("--case-id", type=UUID, required=True)
    evidence.add_argument("--file", type=Path, required=True)
    evidence.add_argument("--provenance", required=True)
    provision = commands.add_parser("import-provision")
    provision.add_argument("--manifest", type=Path, required=True)
    commands.add_parser("stats")
    args = parser.parse_args()
    if args.command == "download-model":
        from app.vectors import download_model
        result = download_model(args.approved_bytes)
    elif args.command == "plan-supreme":
        from app.sources import plan_supreme
        manifest = plan_supreme(args.year, args.limit)
        body = manifest.model_dump_json(indent=2).encode()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(body)
        result = {"manifest": str(args.output), "sha256": hashlib.sha256(body).hexdigest(), "documents": len(manifest.documents), "total_bytes": manifest.total_bytes}
    elif args.command == "acquire":
        from app.ingestion import acquire_batch
        result = acquire_batch(args.manifest, args.approved_sha256, args.max_total_bytes)
    else:
        with writer_session() as session:
            if args.command == "register-sources":
                from app.sources import register_sources
                register_sources(session)
                result = {"registered": "reviewed public-source records; no case or evidence records created"}
            elif args.command == "ingest":
                from app.ingestion import ingest_batch
                result = ingest_batch(session, args.manifest, args.approved_sha256, args.max_total_bytes, args.retry_job)
            elif args.command == "index":
                from app.vectors import index_passages
                result = index_passages(session)
            elif args.command == "search":
                from app.vectors import semantic_search
                result = semantic_search(session, args.query, args.limit)
            elif args.command == "import-evidence":
                from app.ingestion import import_evidence
                record = import_evidence(session, args.case_id, args.file, args.provenance)
                result = {"evidence_id": str(record.id), "sha256": record.sha256, "bytes": record.byte_size}
            elif args.command == "import-provision":
                from app.ingestion import import_provision
                record = import_provision(session, args.manifest)
                result = {"provision_id": str(record.id), "sha256": record.sha256}
            else:
                from app.models import DatasetSource, Judgment, JudgmentPassage, LegalProvision, Evidence
                result = {model.__tablename__: session.scalar(select(func.count()).select_from(model)) for model in [DatasetSource, Judgment, JudgmentPassage, LegalProvision, Evidence]}
                result["indexed_passages"] = session.scalar(select(func.count()).select_from(JudgmentPassage).where(JudgmentPassage.indexed_at.is_not(None)))
    print(json.dumps(result, indent=2, default=str), flush=True)
    if isinstance(result, dict) and result.get("failed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
