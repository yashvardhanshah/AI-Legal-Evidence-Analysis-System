"use client";

import { useCallback, useEffect, useState } from "react";
import { jsonApi } from "./api";

type Job = { id: string; status: string; attempts: number; max_attempts: number; processed: number; total: number; message: string | null; next_attempt_at: string | null };
type Run = { id: string; status: string; page_count: number; original_sha256: string; pipeline_version: string; attempt: number; message: string | null; warnings: string[]; models: { name: string; revision: string; license_id: string }[] };
type Entity = { id: string; text: string; label: string; char_start: number; char_end: number; extractor: string; score: number | null; provenance: { rule_id?: string; score_method?: string } };
type Page = { page_number: number; text: string; text_sha256: string; extraction_method: string; ocr_confidence: number | null; warnings: string[]; entities: Entity[] };
const errorMessage = (error: unknown) => error instanceof Error ? error.message : "Analysis request failed";

export function EvidenceAnalysis({ caseId, evidenceId, mime, canWrite }: { caseId: string; evidenceId: string; mime: string; canWrite: boolean }) {
  const base = `/cases/${caseId}/evidence/${evidenceId}`;
  const supported = ["application/pdf", "image/png", "image/jpeg"].includes(mime);
  const [jobs, setJobs] = useState<Job[]>([]), [runs, setRuns] = useState<Run[]>([]), [selected, setSelected] = useState<Run | null>(null);
  const [page, setPage] = useState<Page | null>(null), [pageNumber, setPageNumber] = useState(1), [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [loaded, setLoaded] = useState(false), [highlight, setHighlight] = useState<Entity | null>(null);
  const active = jobs.some(job => ["queued", "processing"].includes(job.status));
  const load = useCallback(async () => {
    try {
      const [jobData, runData] = await Promise.all([jsonApi(base+"/analysis-jobs"), jsonApi(base+"/analyses")]);
      setJobs(jobData.items); setRuns(runData.items); setLoaded(true); setError("");
    } catch (e) { setError(errorMessage(e)); setRuns([]); setJobs([]); setSelected(null); setPage(null); }
  }, [base]);
  useEffect(() => { if (supported) void load(); }, [load, supported]);
  useEffect(() => { if (!active) return; const timer = setInterval(() => void load(), 2500); return () => clearInterval(timer); }, [active, load]);
  useEffect(() => {
    if (!open || !selected || selected.status !== "completed") return;
    let current = true; setPage(null); setHighlight(null);
    jsonApi(`${base}/analyses/${selected.id}/pages/${pageNumber}`).then(value => { if (current) setPage(value); }).catch(e => { if (current) setError(errorMessage(e)); });
    return () => { current = false; };
  }, [base, open, selected, pageNumber]);

  if (!supported) return <p>Document OCR/NLP supports PDF, PNG and JPEG. Use visual analysis below for MP4 video.</p>;
  async function trigger(reanalyze = false) {
    setBusy(true); setError("");
    try { await jsonApi(base+"/analysis", "POST", { reanalyze }); await load(); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  const completed = runs.filter(run => run.status === "completed");
  const characters = Array.from(page?.text ?? ""); // Match backend Unicode code-point offsets, including non-BMP text.
  return <section aria-label="Document analysis">
    <h3>Document analysis</h3><p>Extracted text and entity candidates require human review. Model scores are not factual confidence or legal findings.</p>
    <div className="actions">{canWrite && <button disabled={busy || active} onClick={() => void trigger()}>{busy ? "Queuing…" : active ? "Analysis in progress" : "Analyze Evidence"}</button>}
      <button disabled={!completed.length || busy} onClick={() => { setSelected(completed[0]); setPageNumber(1); setOpen(value => !value); }}>View Analysis</button>
      <button disabled={busy} onClick={() => void load()}>Refresh analysis status</button>
    </div>
    {error && <p role="alert">{error}</p>}{!loaded && !error && <p role="status">Loading analysis status…</p>}
    {loaded && !jobs.length && <p>No analysis requested yet.</p>}
    {jobs.slice(0, 3).map(job => <div key={job.id}><p role="status">{job.status} · attempt {job.attempts}/{job.max_attempts} · {job.processed}/{job.total || "?"} pages</p>{job.message && <p>{job.message}</p>}
      {canWrite && job.status === "failed" && job.attempts < job.max_attempts && <button disabled={busy || active} onClick={async () => { setBusy(true); try { await jsonApi(`${base}/analysis-jobs/${job.id}/retry`, "POST"); await load(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }}>Retry failed analysis</button>}</div>)}
    {open && selected && <div><label>Completed analysis version<select value={selected.id} onChange={e => { setSelected(completed.find(run => run.id === e.target.value) ?? null); setPageNumber(1); }}>{completed.map(run => <option key={run.id} value={run.id}>{run.pipeline_version} · attempt {run.attempt} · {run.id.slice(0, 8)}</option>)}</select></label>
      <p>Original SHA-256: <code>{selected.original_sha256}</code></p>{selected.models.map(model => <p key={model.name}>{model.name} · {model.revision} · {model.license_id}</p>)}
      <div className="actions"><button disabled={pageNumber <= 1} onClick={() => setPageNumber(pageNumber-1)}>Previous page</button><span>Page {pageNumber} of {selected.page_count}</span><button disabled={pageNumber >= selected.page_count} onClick={() => setPageNumber(pageNumber+1)}>Next page</button></div>
      {!page ? <p role="status">Loading extracted page…</p> : <><p>{page.extraction_method} · text SHA-256: <code>{page.text_sha256}</code></p><p>{page.ocr_confidence === null ? "OCR confidence unavailable for embedded PDF text." : `Tesseract word-confidence mean: ${page.ocr_confidence.toFixed(2)}/100 (not measured accuracy).`}</p>
        {page.warnings.map(warning => <p key={warning}>{warning}</p>)}
        <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: "28rem", overflow: "auto", padding: "12px", border: "1px solid #d2dad6" }}>{highlight ? <>{characters.slice(0, highlight.char_start).join("")}<mark>{characters.slice(highlight.char_start, highlight.char_end).join("")}</mark>{characters.slice(highlight.char_end).join("")}</> : page.text || "No text recognized on this page."}</pre>
        <h4>Source-linked entity candidates</h4>{!page.entities.length ? <p>No supported entity candidates found on this page.</p> : <div style={{ overflowX: "auto" }}><table><thead><tr><th>Type</th><th>Exact text</th><th>Page / offsets</th><th>Extractor</th><th>Reported score</th></tr></thead><tbody>{page.entities.map(entity => <tr key={entity.id}><td>{entity.label}</td><td><button onClick={() => setHighlight(entity)}>{entity.text}</button></td><td>{page.page_number}: [{entity.char_start}, {entity.char_end})</td><td>{entity.extractor === "rule" ? entity.provenance.rule_id : "Pinned DistilBERT NER"}</td><td>{entity.score === null ? "Not scored (literal rule)" : `${entity.score.toFixed(4)} (uncalibrated model score; see provenance)`}</td></tr>)}</tbody></table></div>}
      </>}{canWrite && <button disabled={busy || active} onClick={() => void trigger(true)}>Request new analysis version</button>}
    </div>}
  </section>;
}
