"""Bounded anonymous HTTPS access to the reviewed public judgment bucket."""
from datetime import datetime, timezone
import hashlib
import json
import re
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from app.models import DatasetSource

BUCKET = "https://indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com/"
HOST = urlsplit(BUCKET).hostname
NS = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"


def validate_public_url(url: str):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != HOST or parsed.port not in {None, 443} or parsed.username or parsed.password:
        raise ValueError("Download host is not the reviewed public source")


class RestrictedRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        validate_public_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def fetch(url: str, max_bytes: int, etag: str | None = None) -> bytes:
    validate_public_url(url)
    headers = {"User-Agent": "AcademicLegalEvidence/0.2 (bounded public research subset)"}
    if etag:
        headers["If-Match"] = etag
    with build_opener(RestrictedRedirect()).open(Request(url, headers=headers), timeout=60) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > max_bytes:
            raise ValueError("Source exceeds download budget")
        body = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise ValueError("Source exceeds download budget")
    return body


class DocumentPlan(BaseModel):
    external_id: str = Field(pattern=r"^[0-9_]+$")
    pdf_url: str
    metadata_url: str
    pdf_bytes: int = Field(gt=0, le=20_000_000)
    metadata_bytes: int = Field(gt=0, le=100_000)
    pdf_etag: str
    metadata_etag: str


class BatchPlan(BaseModel):
    source_slug: str = "supreme-court-aws"
    year: int = Field(ge=1950, le=2100)
    license_id: str = "CC-BY-4.0"
    selected_at: str
    total_bytes: int = Field(gt=0, le=60_000_000)
    selection: str = "lexicographic object key; English PDFs with matching metadata"
    documents: list[DocumentPlan] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_manifest(self):
        if self.source_slug != "supreme-court-aws" or self.license_id != "CC-BY-4.0":
            raise ValueError("Unreviewed data source")
        if self.total_bytes != sum(d.pdf_bytes + d.metadata_bytes for d in self.documents):
            raise ValueError("Incorrect manifest byte total")
        if len({d.external_id for d in self.documents}) != len(self.documents):
            raise ValueError("Repeated manifest identity")
        for doc in self.documents:
            expected = f"data/pdf/year={self.year}/english/{doc.external_id}_EN.pdf"
            expected_meta = f"metadata/json/year={self.year}/{doc.external_id}.json"
            if doc.pdf_url != BUCKET + expected or doc.metadata_url != BUCKET + expected_meta:
                raise ValueError("Manifest source path is not canonical")
        return self


def list_objects(prefix: str) -> list[dict]:
    result, token = [], None
    while True:
        params = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            params["continuation-token"] = token
        root = ET.fromstring(fetch(BUCKET + "?" + urlencode(params), 2_000_000))
        for item in root.findall("s:Contents", NS):
            result.append({"key": item.findtext("s:Key", namespaces=NS), "bytes": int(item.findtext("s:Size", namespaces=NS)), "etag": item.findtext("s:ETag", namespaces=NS)})
        token = root.findtext("s:NextContinuationToken", namespaces=NS)
        if not token:
            return result
        if len(result) >= 10_000:
            raise ValueError("Listing exceeds the targeted planning limit")


def plan_supreme(year: int, limit: int = 50) -> BatchPlan:
    if not 1 <= limit <= 100 or not 1950 <= year <= 2100:
        raise ValueError("Invalid bounded batch selection")
    pdfs = list_objects(f"data/pdf/year={year}/english/")
    metadata = {x["key"].rsplit("/", 1)[-1].removesuffix(".json"): x for x in list_objects(f"metadata/json/year={year}/")}
    docs = []
    for pdf in sorted(pdfs, key=lambda x: x["key"]):
        external = pdf["key"].rsplit("/", 1)[-1].removesuffix("_EN.pdf")
        if external not in metadata or not re.fullmatch(r"[0-9_]+", external):
            continue
        meta = metadata[external]
        docs.append(DocumentPlan(external_id=external, pdf_url=BUCKET + pdf["key"], metadata_url=BUCKET + meta["key"], pdf_bytes=pdf["bytes"], metadata_bytes=meta["bytes"], pdf_etag=pdf["etag"], metadata_etag=meta["etag"]))
        if len(docs) == limit:
            break
    return BatchPlan(year=year, selected_at=datetime.now(timezone.utc).isoformat(), total_bytes=sum(d.pdf_bytes+d.metadata_bytes for d in docs), documents=docs)


def register_sources(session):
    records = [
        dict(slug="supreme-court-aws", name="Indian Supreme Court Judgments", publisher="Dattam Labs / vanga dataset project", source_url="https://registry.opendata.aws/indian-supreme-court-judgments/", upstream_url="https://scr.sci.gov.in/", license_id="CC-BY-4.0", license_url=LICENSE_URL, attribution="Indian Supreme Court Judgments, Dattam Labs/vanga; source court Supreme Court of India; accessed via AWS Open Data; CC BY 4.0. Text extraction, OCR and chunking are derived transformations.", status="verified", verified_at=datetime.now(timezone.utc), notes="Public PDF and raw JSON access checked. Source metadata may be incomplete; repository is a mirror, not a certified court copy."),
        dict(slug="high-court-aws", name="Indian High Court Judgments", publisher="Dattam Labs / vanga dataset project", source_url="https://registry.opendata.aws/indian-high-court-judgments/", upstream_url="https://judgments.ecourts.gov.in/", license_id="CC-BY-4.0", license_url=LICENSE_URL, status="verified", verified_at=datetime.now(timezone.utc), attribution="Indian High Court Judgments, Dattam Labs/vanga, AWS Open Data, CC BY 4.0.", notes="Registry/maintainer reviewed; anonymous 2025 court=27_1/bench=hcaurdb partition listing and one PDF HEAD returned 200. No documents acquired; mixed web/mobile identity still requires corpus-specific deduplication before a High Court importer is enabled."),
        dict(slug="india-code", name="India Code", publisher="Legislative Department, Government of India", source_url="https://www.indiacode.nic.in/", upstream_url="https://indiacode.gov.in/", status="blocked", notes="Old site advertises migration. New site access and specific document reuse terms are not yet verified. No statutory text has been imported."),
    ]
    for values in records:
        if not session.scalar(select(DatasetSource).where(DatasetSource.slug == values["slug"])):
            session.add(DatasetSource(**values))
    session.commit()


def parse_supreme_metadata(raw: dict, expected_id: str) -> dict:
    if raw.get("path") != expected_id:
        raise ValueError("Metadata identity differs from PDF identity")
    soup = BeautifulSoup(raw.get("raw_html", ""), "html.parser")
    button = soup.find("button", attrs={"aria-label": re.compile(r"pdf$", re.I)})
    title_node = button.find("strong") if button else None
    title = title_node.get_text(" ", strip=True) if title_node else None
    text = soup.get_text(" ", strip=True)
    date_match = re.search(r"Decision Date\s*:\s*(\d{2}-\d{2}-\d{4})", text)
    when = datetime.strptime(date_match[1], "%d-%m-%Y").date() if date_match else None
    citation = soup.select_one(".escrText")
    return {"title": title, "court": "Supreme Court of India", "judgment_date": when, "citation": citation.get_text(" ", strip=True) if citation else raw.get("nc_display")}
