"use client";

import { useEffect, useRef, useState } from "react";

export function Glyph({ name = "document", size = 20 }: { name?: string; size?: number }) {
  const paths: Record<string, string> = {
    document: "M6 3h8l4 4v14H6z M14 3v5h5 M9 12h6 M9 16h6",
    image: "M3 3h18v18H3z M3 16l5-5 5 5 3-3 5 5 M15 7h.01",
    video: "M3 5h13v14H3z M16 10l5-3v10l-5-3 M8 9l4 3-4 3z",
    upload: "M12 16V3 M7 8l5-5 5 5 M3 15v6h18v-6",
    arrow: "M5 12h14 M13 6l6 6-6 6",
    check: "M5 12l4 4L19 6",
    clock: "M12 8v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
    menu: "M4 6h16 M4 12h16 M4 18h16",
    close: "M6 6l12 12 M18 6L6 18",
    eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12 M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
    layers: "M12 3l10 5-10 5L2 8z M2 12l10 5 10-5 M2 16l10 5 10-5",
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] ?? paths.document}/></svg>;
}

export function StatusBadge({ status }: { status: string }) {
  return <span className="status-badge" data-state={status}><span aria-hidden="true" className="status-dot"/>{status.replaceAll("_", " ")}</span>;
}

export function Loading({ label = "Loading records" }: { label?: string }) {
  return <div className="loading-state" role="status"><span className="loading-ring" aria-hidden="true"/><span>{label}</span><div className="skeleton-lines" aria-hidden="true"><i/><i/><i/></div></div>;
}

export function EmptyState({ title, text, icon = "document" }: { title: string; text: string; icon?: string }) {
  return <div className="empty-state"><span className="empty-icon"><Glyph name={icon} size={26}/></span><h3>{title}</h3><p>{text}</p></div>;
}

export function JobProgress({ job, unit }: { job: { status: string; processed: number; total: number; attempts: number; max_attempts: number }; unit: string }) {
  const known = job.total > 0;
  return <div className="job-progress"><div><StatusBadge status={job.status}/><span>Attempt {job.attempts}/{job.max_attempts}</span></div><progress aria-label={`${unit} processing progress`} max={known ? job.total : 1} value={known ? Math.min(job.processed, job.total) : undefined}/><small>{job.processed}/{known ? job.total : "pending total"} {unit}</small></div>;
}

// Original vector artwork: abstract documents and connected source nodes, never evidence.
export function SourceArtwork() {
  return <svg className="source-artwork" viewBox="0 0 340 240" fill="none" aria-hidden="true"><circle cx="174" cy="121" r="102" stroke="currentColor" strokeOpacity=".13"/><circle cx="174" cy="121" r="76" stroke="currentColor" strokeOpacity=".15" strokeDasharray="4 7"/><path d="M69 91l89 38 106-54 M158 129l83 66 M158 129l-69 65" stroke="currentColor" strokeOpacity=".5"/><rect x="120" y="53" width="103" height="138" rx="12" transform="rotate(9 120 53)" fill="#243D68" stroke="#7894C5"/><rect x="113" y="43" width="103" height="138" rx="12" transform="rotate(-7 113 43)" fill="#F5F8FF"/><path d="M135 75l55-7 M138 92l53-7 M140 109l38-5 M143 126l49-6" stroke="#A4B6D5" strokeWidth="5" strokeLinecap="round"/><circle cx="188" cy="148" r="21" fill="#0D9488"/><path d="M179 148l6 6 12-14" stroke="white" strokeWidth="3" strokeLinecap="round"/><rect x="47" y="69" width="42" height="42" rx="12" fill="#254375" stroke="#6C88B5"/><path d="M59 81h18v18H59z M63 86h10 M63 91h6" stroke="#C9DBFF" strokeWidth="2"/><circle cx="265" cy="72" r="17" fill="#3563E9"/><path d="M258 72h14 M265 65v14" stroke="white" strokeWidth="2"/><circle cx="240" cy="195" r="10" fill="#30B7A9"/><circle cx="85" cy="195" r="7" fill="#7893C2"/></svg>;
}

export function UploadField({ disabled }: { disabled: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");
  const [dragging, setDragging] = useState(false);
  useEffect(() => { const form = input.current?.form; const reset = () => setName(""); form?.addEventListener("reset", reset); return () => form?.removeEventListener("reset", reset); }, []);
  return <label className={`upload-zone ${dragging ? "is-dragging" : ""}`} onDragOver={e => { e.preventDefault(); if (!disabled) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => {
    e.preventDefault(); setDragging(false);
    if (disabled || !input.current || e.dataTransfer.files.length !== 1) return;
    input.current.files = e.dataTransfer.files;
    setName(input.current.files[0]?.name ?? "");
  }}><Glyph name="upload" size={28}/><strong>Drop an original file here, or browse</strong><span>PDF, PNG, JPG, JPEG or MP4. One file at a time.</span><input ref={input} type="file" name="file" accept=".pdf,.png,.jpg,.jpeg,.mp4" required disabled={disabled} onChange={e => setName(e.target.files?.[0]?.name ?? "")}/>{name && <small>Selected: {name}</small>}</label>;
}

export function ArchiveButton({ disabled, onConfirm }: { disabled: boolean; onConfirm: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  return <><button className="secondary" disabled={disabled} onClick={() => dialog.current?.showModal()}>Archive case</button><dialog ref={dialog} className="workspace-dialog" aria-labelledby="archive-title"><span className="eyebrow">CASE STATUS</span><h2 id="archive-title">Archive this case?</h2><p>Evidence stays available. The case becomes read-only and new processing cannot be requested.</p><div className="actions"><button className="secondary" onClick={() => dialog.current?.close()}>Cancel</button><button onClick={() => { dialog.current?.close(); onConfirm(); }}>Confirm archive</button></div></dialog></>;
}
