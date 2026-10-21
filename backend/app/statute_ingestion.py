"""Operator-only exact-span import of rights-reviewed official statute versions.

No network access. Never enables a blocked source or guesses commencement/crosswalks.
The manifest and PDF are private runtime files, not source-code fixtures.
"""
import argparse,hashlib,json,re,copy
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,model_validator
from sqlalchemy import select,text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_engine
from app.documents import extract_pdf,chunk_pages
from app.models import DatasetSource,StatuteVersion,LegalProvision,ProvisionPassage,AuditLog
from app.storage import PrivateStorage
from app import vectors,legal_retrieval

HOSTS={'indiacode.nic.in','www.indiacode.nic.in','indiacode.gov.in','www.indiacode.gov.in','egazette.gov.in'}

class Span(BaseModel):
    model_config=ConfigDict(extra='forbid')
    page_number:int=Field(gt=0)
    char_start:int=Field(ge=0)
    char_end:int=Field(gt=0)
    sha256:str=Field(pattern='^[0-9a-f]{64}$')

class Section(BaseModel):
    model_config=ConfigDict(extra='forbid')
    identifier:str=Field(pattern=r'^\d+[A-Z]?$')
    heading:str=Field(min_length=3,max_length=1000)
    spans:list[Span]=Field(min_length=1,max_length=100)
    effective_from:date|None
    effective_to:date|None=None
    commencement_reference:str=Field(min_length=10)
    applicability_note:str=Field(min_length=10)
    full_section_reviewed:bool
    @model_validator(mode='after')
    def dates(self):
        if self.effective_to and (not self.effective_from or self.effective_to<self.effective_from):raise ValueError('Invalid effective interval')
        if not self.full_section_reviewed:raise ValueError('Complete section boundaries require human review')
        return self

class Manifest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_slug:str
    act_identifier:str=Field(min_length=3,max_length=255)
    act_title:str=Field(min_length=10)
    version:str=Field(min_length=3,max_length=255)
    source_url:str
    document_path:Path
    sha256:str=Field(pattern='^[0-9a-f]{64}$')
    publication_on:date
    consolidated_on:date
    rights_reference:str=Field(min_length=10)
    rights_basis:str=Field(min_length=20)
    amendments_review:str=Field(min_length=20)
    verified_by:str=Field(min_length=3)
    sections:list[Section]=Field(min_length=1,max_length=1000)
    @model_validator(mode='after')
    def official(self):
        parsed=urlsplit(self.source_url)
        if parsed.scheme!='https' or parsed.hostname not in HOSTS or parsed.username or parsed.password:raise ValueError('Official HTTPS source required')
        if self.consolidated_on<self.publication_on:raise ValueError('Consolidation precedes publication')
        if len({s.identifier for s in self.sections})!=len(self.sections):raise ValueError('Duplicate section identifier')
        return self

def exact_sections(pages,manifest):
    used={};output=[]
    for section in manifest.sections:
        fragments=[];last=(0,0)
        for span in section.spans:
            if span.page_number>len(pages):raise ValueError('Missing source page')
            page=pages[span.page_number-1]
            if not 0<=span.char_start<span.char_end<=len(page):raise ValueError('Invalid exact page offsets')
            if (span.page_number,span.char_start)<last:raise ValueError('Unordered section spans')
            last=(span.page_number,span.char_end)
            for start,end in used.get(span.page_number,[]):
                if span.char_start<end and span.char_end>start:raise ValueError('Overlapping statutory sections')
            used.setdefault(span.page_number,[]).append((span.char_start,span.char_end))
            literal=page[span.char_start:span.char_end]
            if legal_retrieval.digest(literal)!=span.sha256:raise ValueError('Exact source span hash differs')
            fragments.append((span,literal))
        first=fragments[0][1]
        if not re.match(r'^\s*'+re.escape(section.identifier)+r'\.\s+',first) or section.heading not in first:
            raise ValueError('Section identifier/heading is not present at the reviewed source boundary')
        output.append((section,fragments))
    return output

def import_version(db,manifest_path):
    manifest=Manifest.model_validate_json(Path(manifest_path).read_bytes())
    # Serialize operator imports/indexing without changing old legal or vector records.
    db.execute(text('SELECT pg_advisory_xact_lock(60062026)'))
    source=db.scalar(select(DatasetSource).where(DatasetSource.slug==manifest.source_slug))
    if not source or source.status!='verified' or not source.license_id or not source.license_url or not source.verified_at:
        raise ValueError('Statute ingestion disabled: source access and reuse permission must first be verified')
    if manifest.document_path.stat().st_size>get_settings().max_file_bytes:raise ValueError('Official PDF exceeds size limit')
    body=manifest.document_path.read_bytes()
    if hashlib.sha256(body).hexdigest()!=manifest.sha256:raise ValueError('Official original hash mismatch')
    pages,_=extract_pdf(body,get_settings().max_pdf_pages)
    title=' '.join(manifest.act_title.lower().split())
    if title not in ' '.join(' '.join(pages[:8]).lower().split()):raise ValueError('Act title missing from actual source document')
    parsed=exact_sections(pages,manifest)
    existing=db.scalar(select(StatuteVersion).where(StatuteVersion.source_id==source.id,StatuteVersion.act_identifier==manifest.act_identifier,StatuteVersion.version==manifest.version))
    if existing:
        if existing.sha256!=manifest.sha256 or existing.metadata_record.get('manifest_sha256')!=hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest():
            raise ValueError('Immutable statute version differs; review a new version identifier')
        return existing
    stored=PrivateStorage(get_settings().private_root).put(body)
    version=StatuteVersion(source_id=source.id,act_identifier=manifest.act_identifier,version=manifest.version,source_url=manifest.source_url,
        storage_key=stored.key,sha256=stored.sha256,publication_on=manifest.publication_on,consolidated_on=manifest.consolidated_on,
        metadata_record=dict(rights_reference=manifest.rights_reference,rights_basis=manifest.rights_basis,license_id=source.license_id,
            amendments_review=manifest.amendments_review,verified_by=manifest.verified_by,manifest_sha256=hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest(),
            legal_applicability='Snapshot and reviewed commencement metadata only; not an automatic current-law determination'))
    db.add(version);db.flush()
    for section,fragments in parsed:
        content='\n'.join(fragment for _,fragment in fragments)
        law=LegalProvision(source_id=source.id,act_identifier=manifest.act_identifier,act_title=manifest.act_title,version=manifest.version,
            provision_identifier=section.identifier,heading=section.heading,text=content,source_url=manifest.source_url,source_document_sha256=stored.sha256,
            storage_key=stored.key,page_number=fragments[0][0].page_number,effective_from=section.effective_from,effective_to=section.effective_to,sha256=legal_retrieval.digest(content))
        db.add(law);db.flush();ordinal=0
        section_meta=copy.deepcopy(version.metadata_record);section_meta.setdefault('sections',{})[section.identifier]=dict(commencement_reference=section.commencement_reference,applicability_note=section.applicability_note)
        version.metadata_record=section_meta
        for span,fragment in fragments:
            for chunk in chunk_pages([fragment],vectors.tokenizer()):
                db.add(ProvisionPassage(version_id=version.id,provision_id=law.id,ordinal=ordinal,page_number=span.page_number,
                    char_start=span.char_start+chunk['char_start'],char_end=span.char_start+chunk['char_end'],text=chunk['text'],sha256=chunk['text_sha256']))
                ordinal+=1
    db.add(AuditLog(actor=manifest.verified_by,action='statute.version_imported',resource_type='statute_version',resource_id=version.id,
        details=dict(sha256=stored.sha256,sections=len(parsed))))
    db.commit();return version

def index(db):
    db.execute(text('SELECT pg_advisory_lock(60062027)'))
    try:
        rows=list(db.scalars(select(ProvisionPassage).join(StatuteVersion).join(DatasetSource,DatasetSource.id==StatuteVersion.source_id).where(
            DatasetSource.status=='verified',DatasetSource.license_id.is_not(None),ProvisionPassage.vector_id.is_(None))))
        if not rows:return dict(newly_indexed=0)
        store=legal_retrieval.statute_collection()
        for start in range(0,len(rows),32):
            batch=rows[start:start+32]
            for passage in batch:
                if legal_retrieval.digest(passage.text)!=passage.sha256:raise ValueError('Statutory passage hash mismatch')
                version=db.get(StatuteVersion,passage.version_id)
                PrivateStorage(get_settings().private_root).read_verified(version.storage_key,version.sha256)
            embeddings=vectors.embedder().encode([p.text for p in batch],normalize_embeddings=True,show_progress_bar=False).tolist()
            store.upsert(ids=[str(p.id) for p in batch],embeddings=embeddings,metadatas=[dict(text_sha256=p.sha256,version_id=str(p.version_id)) for p in batch])
            for p in batch:p.vector_id,p.embedding_revision=str(p.id),get_settings().embedding_revision
            db.commit()
        return dict(newly_indexed=len(rows),statute_vectors=store.count())
    finally:
        db.execute(text('SELECT pg_advisory_unlock(60062027)'));db.commit()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--manifest',type=Path);parser.add_argument('--index',action='store_true')
    args=parser.parse_args()
    if not args.manifest and not args.index:parser.error('Choose an explicitly reviewed manifest or --index')
    with Session(get_engine()) as db:
        if args.manifest:
            version=import_version(db,args.manifest);print(json.dumps(dict(version_id=str(version.id),sha256=version.sha256)))
        if args.index:print(json.dumps(index(db)))
