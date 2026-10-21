"""Offline source-only retrieval. Distances are not legal correctness probabilities."""
from datetime import date
import hashlib
from functools import lru_cache

from sqlalchemy import select,func,or_
from app import vectors
from app.config import get_settings
from app.models import Judgment,JudgmentPassage,DatasetSource,LegalProvision,ProvisionPassage,StatuteVersion

NOTICE='Research candidates only; source authenticity does not establish legal applicability. Distances are not probabilities. Verify the original, legal version, incident date and later authorities with qualified counsel.'
CATALOG=[dict(act_identifier=act,title=title,source_url=url,status='blocked',reason='Official current access, reuse permission, commencement exceptions and amendment/version coverage are not fully verified; no statutory text imported.') for act,title,url in [
 ('BNS-2023','Bharatiya Nyaya Sanhita, 2023','https://www.indiacode.nic.in/handle/123456789/20062'),
 ('BNSS-2023','Bharatiya Nagarik Suraksha Sanhita, 2023','https://www.indiacode.nic.in/handle/123456789/20099'),
 ('BSA-2023','Bharatiya Sakshya Adhiniyam, 2023','https://www.indiacode.nic.in/handle/123456789/20063')]]

def digest(text): return hashlib.sha256(text.encode()).hexdigest()

def query_vector(query):
    if len(vectors.tokenizer().encode(query,add_special_tokens=True,truncation=False))>256:
        raise vectors.QueryTooLong('Query exceeds 256 model tokens; shorten the question')
    return vectors.embedder().encode([query],normalize_embeddings=True,show_progress_bar=False).tolist()

@lru_cache
def statute_collection():
    import chromadb
    from chromadb.config import Settings
    config=get_settings()
    store=chromadb.PersistentClient(path=str(config.private_root.resolve()/'chroma-statutes'),settings=Settings(anonymized_telemetry=False,allow_reset=False))
    result=store.get_or_create_collection('verified_provision_passages_minilm_v1',embedding_function=None,
        metadata={'hnsw:space':'cosine','model':config.embedding_model,'revision':config.embedding_revision})
    if result.metadata.get('revision')!=config.embedding_revision or result.metadata.get('hnsw:space')!='cosine':
        raise vectors.VectorUnavailable('Statutory index provenance mismatch')
    return result

def judgments(db,query,limit,filters):
    eligible=select(Judgment)
    if filters.get('court'): eligible=eligible.where(Judgment.court==filters['court'])
    if filters.get('year'): eligible=eligible.where(func.extract('year',Judgment.judgment_date)==filters['year'])
    if filters.get('source_id'): eligible=eligible.where(Judgment.source_id==filters['source_id'])
    records={str(j.id):j for j in db.scalars(eligible)}
    if not records:return []
    store=vectors.collection()
    count=store.count()
    if not count:raise vectors.VectorUnavailable('Judgment corpus is not indexed')
    matches=store.query(query_embeddings=query_vector(query),n_results=min(count,5000),
        where={'judgment_id':{'$in':list(records)}},include=['distances','metadatas'])
    rows=db.scalars(select(JudgmentPassage).where(JudgmentPassage.vector_id.in_(matches['ids'][0]),
        JudgmentPassage.embedding_revision==get_settings().embedding_revision))
    by_vector={p.vector_id:p for p in rows}
    output=[];seen=set()
    for vector_id,distance,meta in zip(matches['ids'][0],matches['distances'][0],matches['metadatas'][0]):
        p=by_vector.get(vector_id)
        if not p or str(p.judgment_id) not in records or p.judgment_id in seen:continue
        j=records[str(p.judgment_id)]
        if p.text_sha256!=digest(p.text) or meta.get('text_sha256')!=p.text_sha256 or meta.get('judgment_id')!=str(j.id):continue
        seen.add(j.id)
        output.append(dict(kind='judgment',source_id=str(j.source_id),document_id=str(j.id),passage_id=str(p.id),title=j.title,
            court=j.court,judgment_date=j.judgment_date.isoformat() if j.judgment_date else None,citation=j.citation,
            source_url=j.source_url,document_sha256=j.sha256,page_number=p.page_number,char_start=p.char_start,char_end=p.char_end,
            excerpt=p.text,text_sha256=p.text_sha256,distance=float(distance),metric='cosine_distance',
            model=get_settings().embedding_model,model_revision=get_settings().embedding_revision,classification='verified_source_text'))
        if len(output)==limit:break
    return output

def statutes(db,query,limit,filters):
    query_sql=select(ProvisionPassage,LegalProvision,StatuteVersion).join(LegalProvision,LegalProvision.id==ProvisionPassage.provision_id).join(StatuteVersion,StatuteVersion.id==ProvisionPassage.version_id).join(DatasetSource,DatasetSource.id==StatuteVersion.source_id).where(
        DatasetSource.status=='verified',DatasetSource.license_id.is_not(None),ProvisionPassage.embedding_revision==get_settings().embedding_revision)
    for key,column in [('act',LegalProvision.act_identifier),('version',LegalProvision.version),('source_id',LegalProvision.source_id)]:
        if filters.get(key):query_sql=query_sql.where(column==filters[key])
    if filters.get('as_of'):
        when=date.fromisoformat(str(filters['as_of']))
        query_sql=query_sql.where(LegalProvision.effective_from<=when,or_(LegalProvision.effective_to.is_(None),LegalProvision.effective_to>=when))
    rows={p.vector_id:(p,law,version) for p,law,version in db.execute(query_sql) if p.vector_id}
    if not rows:return []
    store=statute_collection()
    if not store.count():raise vectors.VectorUnavailable('Verified statutory passages are not indexed')
    matches=store.query(query_embeddings=query_vector(query),n_results=min(store.count(),5000),include=['distances','metadatas'])
    output=[];seen=set()
    for vector_id,distance,meta in zip(matches['ids'][0],matches['distances'][0],matches['metadatas'][0]):
        if vector_id not in rows:continue
        p,law,version=rows[vector_id]
        if law.id in seen or p.sha256!=digest(p.text) or meta.get('text_sha256')!=p.sha256 or meta.get('version_id')!=str(version.id):continue
        seen.add(law.id)
        output.append(dict(kind='statute',source_id=str(law.source_id),document_id=str(version.id),passage_id=str(p.id),provision_id=str(law.id),
            title=law.act_title,act_identifier=law.act_identifier,section=law.provision_identifier,heading=law.heading,version=law.version,
            effective_from=law.effective_from.isoformat() if law.effective_from else None,effective_to=law.effective_to.isoformat() if law.effective_to else None,
            version_metadata=version.metadata_record,source_url=law.source_url,document_sha256=version.sha256,page_number=p.page_number,
            char_start=p.char_start,char_end=p.char_end,excerpt=p.text,text_sha256=p.sha256,distance=float(distance),metric='cosine_distance',
            model=get_settings().embedding_model,model_revision=get_settings().embedding_revision,classification='verified_source_text'))
        if len(output)==limit:break
    return output

def search(db,query,limit=5,**filters):
    kind=filters.pop('kind','all')
    # Even an empty corpus must enforce the documented query context limit.
    if len(vectors.tokenizer().encode(query,add_special_tokens=True,truncation=False))>256:raise vectors.QueryTooLong('Query exceeds 256 model tokens')
    js=judgments(db,query,limit,filters) if kind in ['all','judgment'] else []
    ss=statutes(db,query,limit,filters) if kind in ['all','statute'] else []
    return dict(query=query,judgments=js,statutes=ss,statute_status='available' if ss else 'insufficient_statutory_sources',
        metric='cosine_distance',lower_is_better=True,notice=NOTICE,algorithm='extractive-retrieval-v1',llm_enabled=False)
