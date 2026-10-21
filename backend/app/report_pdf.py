"""Local deterministic PDF renderer. Untrusted text is escaped, never interpreted."""
import io
from pathlib import Path
from xml.sax.saxutils import escape
import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, KeepTogether
from pypdf import PdfReader
from app.report_sources import ReportFailure


def render(snapshot, snapshot_sha256):
    font_path = Path(reportlab.__file__).parent/'fonts'/'Vera.ttf'
    if 'ReportVera' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('ReportVera', str(font_path)))
    supported = pdfmetrics.getFont('ReportVera').face.charToGlyph

    def safe(value):
        text = str(value) if value is not None else 'Not recorded'
        text = ''.join(c if ord(c) in supported or c in '\n\t' else f'[U+{ord(c):04X}]' for c in text)
        return escape(text).replace('\n', '<br/>')

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='ReportBody', fontName='ReportVera', fontSize=9, leading=13, spaceAfter=7, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='ReportHeading', parent=styles['ReportBody'], fontSize=15, leading=20, spaceBefore=14, spaceAfter=9, keepWithNext=True, textColor=colors.HexColor('#18344d')))
    styles.add(ParagraphStyle(name='ReportTitle', parent=styles['ReportHeading'], fontSize=23, leading=30, alignment=TA_CENTER, spaceAfter=20))
    story = []

    def paragraph(value, style='ReportBody'):
        # Split very long source text into bounded flowables, without dropping characters.
        text = str(value) if value is not None else 'Not recorded'
        for start in range(0, max(1, len(text)), 1500):
            story.append(Paragraph(safe(text[start:start+1500]), styles[style]))

    def heading(value):
        paragraph(value, 'ReportHeading')

    def details(item, keys):
        for key in keys.split():
            paragraph(f'{key.replace("_", " ").capitalize()}: {item.get(key)}')

    case = snapshot['case']
    paragraph(snapshot['title'], 'ReportTitle')
    paragraph('CONFIDENTIAL — AUTHORIZED CASE USERS ONLY')
    paragraph('REVIEW COPY — approval status is recorded externally')
    details(snapshot, 'report_id version captured_at requested_by')
    paragraph(f'Case: {case["reference"]} / {case["id"]}')
    paragraph('Source-grounded investigation compilation. This PDF alone is not a finalized investigation or a determination of guilt, liability or admissibility.')
    story.append(PageBreak())
    heading('Executive Summary — recorded data, no inferred conclusions')
    paragraph(f'Case title (user-entered record): {case["title"]}')
    paragraph(f'Case description (user-entered record): {case["description"] or "No description recorded."}')
    count = snapshot['coverage']
    paragraph(f'Retained sources: {count["evidence"]} evidence records; {count["document_analyses"]} completed document analyses; {count["visual_analyses"]} completed visual analyses; {count["research_runs"]} completed research runs; {count["human_reviews"]} attributed relevance annotations.')
    paragraph(snapshot['selection_policy'])
    paragraph('Verified statutory analysis is unavailable. No BNS, BNSS, BSA or legacy statutory provisions have been imported.')
    heading('Case Information — user-entered records')
    details(case, 'id reference title description jurisdiction status owner_id opened_on incident_on created_at updated_at archived_at')
    for person in snapshot['participants']:
        paragraph(f'Authorized participant at snapshot: {person["display_name"]}; ID {person["id"]}; role {person["role"]}; active {person["is_active"]}')
    if snapshot['evidence']:
        heading('Evidence Inventory — preserved source records')
        for item in snapshot['evidence']:
            details(item, 'id original_filename mime_type byte_size created_at captured_on uploader_id provenance sha256')
            story.append(Spacer(1, 8))
    if snapshot['documents']:
        heading('Document Analysis — unverified automated observations')
        for doc in snapshot['documents']:
            details(doc, 'id evidence_id original_sha256 pipeline_version artifact_id ner_model_id ocr_model_id created_at finished_at warnings')
            for page in doc['pages']:
                paragraph(f'Page {page["page_number"]}; page ID {page["id"]}; extraction {page["extraction_method"]}; OCR confidence {page["ocr_confidence"]}; page text SHA-256 {page["text_sha256"]}')
                paragraph('Exact retained page text (automatically extracted, unverified):')
                paragraph(page['text'])
                for entity in page['entities']:
                    paragraph(f'Entity candidate {entity["id"]}: {entity["label"]} / {entity["text"]}; page {page["page_number"]}; Unicode offsets [{entity["char_start"]},{entity["char_end"]}); extractor {entity["extractor"]}; model {entity["model_id"]}; score {entity["score"]}. Not an established fact.')
    if snapshot['visuals']:
        heading('Visual Evidence Analysis — model observations, not findings')
        for visual in snapshot['visuals']:
            details(visual, 'id evidence_id original_sha256 model_id pipeline_version settings media')
            paragraph('Each frame is an individual sampled observation, not continuous tracking or identification.')
            for frame in visual['frames']:
                paragraph(f'Frame {frame["frame_index"]}; actual timestamp {frame["timestamp_ms"]} ms; dimensions {frame["width"]} x {frame["height"]}; frame ID {frame["id"]}; pixel SHA-256 {frame["pixel_sha256"]}; source artifact {frame["source_artifact_id"]}; annotated artifact {frame["annotated_artifact_id"]}')
                for detection in frame['detections']:
                    paragraph(f'Object candidate {detection["id"]}: class {detection["class_id"]} / {detection["label"]}; model confidence {detection["confidence"]}; pixel xyxy [{detection["x1"]}, {detection["y1"]}, {detection["x2"]}, {detection["y2"]}].')
                if not frame['detections']:
                    paragraph('No retained detections in this sampled frame at the configured model threshold.')
    if snapshot['research']:
        heading('Legal Research — actual retrieved judgments, no legal conclusions')
        for run in snapshot['research']:
            paragraph(f'Research run {run["id"]}; outcome {run["outcome"]}; captured completion {run["finished_at"]}')
            for selected in run['inputs']:
                paragraph(f'Input {selected["id"]}; evidence {selected["evidence_id"]}; page {selected["page_id"]}; SHA-256 {selected["sha256"]}; provenance {selected["provenance"]}')
                paragraph(f'Exact retained query: {selected["query"]}')
            for result in run['results']:
                citation = result['citation']
                paragraph(f'Source result {result["id"]}; input {result["input_id"]}; judgment {citation["document_id"]}; passage {citation["passage_id"]}')
                details(citation, 'title court judgment_date citation source_url page_number char_start char_end document_sha256 text_sha256 distance model model_revision')
                paragraph('Exact source excerpt — source correspondence does not establish applicability:')
                paragraph(citation['excerpt'])
    if snapshot['human_reviews']:
        heading('Human Review Findings — attributed interpretations, not automated facts')
        for review in snapshot['human_reviews']:
            paragraph(f'Reviewer {review["reviewer_name"]} ({review["reviewer_id"]}); {review["created_at"]}; result {review["result_id"]}; disposition {review["disposition"]}; review {review["id"]}')
            paragraph(review['note'])
    heading('Limitations and Uncertainties')
    for value in snapshot['limitations']:
        paragraph(value)
    for item in snapshot['evidence']:
        if item['id'] not in {d['evidence_id'] for d in snapshot['documents']}:
            paragraph(f'No completed document analysis included for evidence {item["id"]}.')
        if item['id'] not in {d['evidence_id'] for d in snapshot['visuals']}:
            paragraph(f'No completed visual analysis included for evidence {item["id"]}.')
    heading('Evidence Integrity Appendix')
    paragraph(f'Pipeline: {snapshot["schema"]}; snapshot SHA-256: {snapshot_sha256}')
    paragraph('The final PDF SHA-256 is recorded externally in authorized report metadata, audit completion and reviewer decisions. A PDF cannot contain its own final hash. The exact JSON snapshot is separately downloadable and hash verified.')
    for source in snapshot['verified_sources']:
        paragraph(f'Original verified at generation: {source}')
    for artifact in snapshot['artifacts']:
        paragraph(f'Verified derived artifact: {artifact}')
    for model in snapshot['models']:
        details(model, 'id name revision task license_id source_url byte_size file_hashes software')
    for source in snapshot['dataset_sources']:
        details(source, 'id name publisher source_url upstream_url license_id license_url attribution verified_at')
    paragraph('Embedded font copyright and permission notice:')
    font_license = (font_path.parent/'bitstream-vera-license.txt').read_text(encoding='utf-8').split('Copyright FAQ')[0]
    paragraph(font_license)
    paragraph('Post-generation reviewer annotations and terminal approval/rejection decisions are append-only external records, bound to this PDF hash and snapshot hash. They cannot change this report version.')

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=44, leftMargin=44, topMargin=53, bottomMargin=48,
        title=snapshot['title'], author='AI Legal Evidence Analysis System — deterministic compilation')

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#425466'))
        canvas.drawString(44, 25, f'Report {snapshot["report_id"]} | v{snapshot["version"]} | Review copy')
        canvas.drawRightString(A4[0]-44, 25, f'Page {document.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    data = output.getvalue()
    pages = len(PdfReader(io.BytesIO(data)).pages)
    if not 1 <= pages <= 2000 or len(data) > 50_000_000:
        raise ReportFailure('report_limit_exceeded')
    return data, pages
