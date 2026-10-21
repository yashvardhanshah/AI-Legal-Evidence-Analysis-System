"use client";

import { useCallback, useEffect, useState } from "react";
import { api, jsonApi } from "./api";

type Job = { id: string; status: string; processed: number; total: number; attempts: number; max_attempts: number; message: string | null };
type Run = { id: string; status: string; frame_count: number; original_sha256: string; pipeline_version: string; media: { kind?: string; sampling?: string; timestamp_basis?: string; fps?: number }; settings: { interpretation?: string }; model: { name: string; revision: string; license_id: string } | null };
type Detection = { id: string; label: string; class_id: number; confidence: number; x1: number; y1: number; x2: number; y2: number };
type Frame = { id: string; frame_index: number; timestamp_ms: number; width: number; height: number; pixel_sha256: string; inference_ms: number; detections: Detection[] };
const message = (e: unknown) => e instanceof Error ? e.message : "Visual analysis request failed";

export function VisualAnalysis({ caseId, evidenceId, mime, canWrite }: { caseId: string; evidenceId: string; mime: string; canWrite: boolean }) {
  const base = `/cases/${caseId}/evidence/${evidenceId}`;
  const supported = ["image/png", "image/jpeg", "video/mp4"].includes(mime);
  const [jobs, setJobs] = useState<Job[]>([]), [runs, setRuns] = useState<Run[]>([]), [selected, setSelected] = useState<Run | null>(null);
  const [frame, setFrame] = useState<Frame | null>(null), [offset, setOffset] = useState(0), [open, setOpen] = useState(false);
  const [source, setSource] = useState(""), [annotated, setAnnotated] = useState(""), [busy, setBusy] = useState(false), [error, setError] = useState(""), [loaded, setLoaded] = useState(false);
  const active = jobs.some(j => ["queued", "processing"].includes(j.status));
  const load = useCallback(async () => {
    try {
      const [j, r] = await Promise.all([jsonApi(base+"/visual-jobs"), jsonApi(base+"/visual-analyses")]);
      setJobs(j.items); setRuns(r.items); setLoaded(true); setError("");
    } catch (e) { setError(message(e)); setJobs([]); setRuns([]); setSelected(null); setFrame(null); setSource(""); setAnnotated(""); }
  }, [base]);
  useEffect(() => { if (supported) void load(); }, [supported, load]);
  useEffect(() => { if (!active) return; const timer = setInterval(() => void load(), 2500); return () => clearInterval(timer); }, [active, load]);
  useEffect(() => {
    let current = true; const urls: string[] = [];
    setFrame(null); setSource(""); setAnnotated("");
    if (!open || !selected) return;
    void (async () => {
      try {
        const data = await jsonApi(`${base}/visual-analyses/${selected.id}/frames?limit=1&offset=${offset}`);
        const next: Frame | undefined = data.items[0];
        if (!next) throw new Error("No published sampled frame available");
        const path = `${base}/visual-analyses/${selected.id}/frames/${next.id}/artifact`;
        const responses = await Promise.all([api(path+"?annotated=false"), api(path)]);
        const blobs = await Promise.all(responses.map(async response => {
          const blob = await response.blob();
          const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await blob.arrayBuffer()))).map(v => v.toString(16).padStart(2,"0")).join("");
          if (hash !== response.headers.get("x-content-sha256")) throw new Error("Visual artifact failed SHA-256 verification");
          return blob;
        }));
        if (!current) return;
        urls.push(...blobs.map(blob => URL.createObjectURL(blob)));
        setFrame(next); setSource(urls[0]); setAnnotated(urls[1]); setError("");
      } catch (e) { if (current) setError(message(e)); }
    })();
    return () => { current = false; urls.forEach(url => URL.revokeObjectURL(url)); };
  }, [base, open, selected, offset]);
  if (!supported) return null;
  const completed = runs.filter(r => r.status === "completed");
  async function trigger(reanalyze = false) {
    setBusy(true); setError("");
    try { await jsonApi(base+"/visual-analysis", "POST", { reanalyze }); await load(); }
    catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  return <section aria-label="Visual evidence analysis">
    <h3>Visual object candidates</h3><p>Object detections do not identify people, establish intent, or prove that a crime occurred. Video results cover sampled frames, with no continuous tracking.</p>
    <div className="actions">{canWrite && <button disabled={busy || active} onClick={() => void trigger()}>{active ? "Visual analysis in progress" : mime === "video/mp4" ? "Analyze Video" : "Analyze Image"}</button>}
      <button disabled={!completed.length || busy} onClick={() => { setSelected(completed[0]); setOffset(0); setOpen(value => !value); }}>View Results</button>
      <button disabled={busy} onClick={() => void load()}>Refresh visual status</button></div>
    {error && <p role="alert">{error}</p>}{!loaded && !error && <p role="status">Loading visual status...</p>}{loaded && !jobs.length && <p>No visual analysis requested yet.</p>}
    {jobs.slice(0,3).map(job => <div key={job.id}><p role="status">{job.status}: {job.processed}/{job.total || "?"} sample budget, attempt {job.attempts}/{job.max_attempts}</p>{job.message && <p>{job.message}</p>}
      {canWrite && job.status === "failed" && job.attempts < job.max_attempts && <button disabled={busy || active} onClick={async () => { setBusy(true); try { await jsonApi(`${base}/visual-jobs/${job.id}/retry`,"POST"); await load(); } catch (e) { setError(message(e)); } finally { setBusy(false); } }}>Retry visual analysis</button>}</div>)}
    {open && selected && <div><label>Visual analysis version<select value={selected.id} onChange={e => { setSelected(completed.find(r => r.id === e.target.value) ?? null); setOffset(0); }}>{completed.map(r => <option key={r.id} value={r.id}>{r.pipeline_version} {r.id.slice(0,8)}</option>)}</select></label>
      <p>Original SHA-256: <code>{selected.original_sha256}</code></p>{selected.model && <p>{selected.model.name} / {selected.model.revision} / {selected.model.license_id}</p>}
      {selected.media.sampling && <p>{selected.media.sampling}</p>}{selected.media.timestamp_basis && <p>{selected.media.timestamp_basis}</p>}
      <div className="actions"><button disabled={!offset} onClick={() => setOffset(offset-1)}>Previous sampled frame</button><span>Sample {offset+1} of {selected.frame_count}</span><button disabled={offset+1 >= selected.frame_count} onClick={() => setOffset(offset+1)}>Next sampled frame</button></div>
      {!frame ? <p role="status">Loading authenticated visual artifacts...</p> : <><p>Source frame {frame.frame_index}; elapsed presentation timestamp {frame.timestamp_ms.toFixed(3)} ms; {frame.width} x {frame.height}; inference {frame.inference_ms.toFixed(2)} ms. Artifact hashes verified.</p>
        <p>Decoded BGR pixel SHA-256: <code>{frame.pixel_sha256}</code></p>
        <figure><img src={source} alt={`Unannotated source sample at frame ${frame.frame_index}`} style={{maxWidth:"100%",maxHeight:"28rem"}} /><figcaption>Decoded source derivative; original evidence unchanged.</figcaption></figure>
        <figure><img src={annotated} alt={`YOLOX annotations for frame ${frame.frame_index}`} style={{maxWidth:"100%",maxHeight:"28rem"}} /><figcaption>Actual YOLOX object candidates; scores are uncalibrated.</figcaption></figure>
        {!frame.detections.length ? <p>No supported object candidate exceeded the configured threshold in this sample.</p> : <div style={{overflowX:"auto"}}><table><thead><tr><th>Class</th><th>Reported score</th><th>Source-pixel box (x1,y1,x2,y2)</th></tr></thead><tbody>{frame.detections.map(d => <tr key={d.id}><td>{d.label} ({d.class_id})</td><td>{d.confidence.toFixed(4)}</td><td>{[d.x1,d.y1,d.x2,d.y2].map(v => v.toFixed(2)).join(", ")}</td></tr>)}</tbody></table></div>}</>}
      {canWrite && <button disabled={busy || active} onClick={() => void trigger(true)}>Request new visual version</button>}
    </div>}
  </section>;
}
