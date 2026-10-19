"use client";

import { useCallback, useEffect, useState } from "react";

type Health = { status: string; database: string; migration?: string };
const modules = [
  ["02", "Data foundation", "Schema, private storage and verified public sources"],
  ["03", "Case workspace", "Authentication, case access and evidence uploads"],
  ["04–06", "Evidence intelligence", "Document processing, visual analysis and legal retrieval"],
  ["07–08", "Review & reporting", "Source-grounded reports, evaluation and security checks"],
];

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/system", { cache: "no-store", signal: AbortSignal.timeout(7000) });
      const data = await response.json();
      setHealth(data);
    } catch { setHealth({ status: "unavailable", database: "unavailable" }); }
    finally { setLoading(false); setCheckedAt(new Date().toLocaleTimeString()); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const connected = health?.status === "ok";

  return <div className="workspace">
    <aside className="sidebar">
      <a href="/" className="brand"><span className="brand-mark" aria-hidden="true">§</span><span>LEGAL EVIDENCE<small>ANALYSIS SYSTEM</small></span></a>
      <p className="nav-label">WORKSPACE</p>
      <nav aria-label="Main navigation">
        <a className="nav-active" href="/">◈ <span>Overview</span></a>
        {["Cases", "Evidence library", "Legal research", "Reports"].map(label => <button key={label} disabled title="Available in a later phase"><span aria-hidden="true">◇</span> {label}<small>Planned</small></button>)}
      </nav>
      <div className="sidebar-note"><span className="tiny-label">ACADEMIC PROJECT</span><p>Built for careful inquiry.<br />Designed for human review.</p><span>India · Development workspace</span></div>
    </aside>
    <div className="main-shell">
      <header><span>Workspace <span className="breadcrumb">/ Overview</span></span><span className="environment"><i /> Local development</span></header>
      <main>
        <div className="page-heading"><div><p className="eyebrow">FOUNDATION / PHASE 01</p><h1>A clearer view of the evidence.</h1><p className="subtitle">Your legal research and investigation workspace starts here.</p></div><span className="phase-badge">Foundation preview</span></div>
        <section className="hero" aria-labelledby="foundation-title"><div><span className="tiny-label">BUILDING THE FOUNDATION</span><h2 id="foundation-title">One workspace.<br />Every source accounted for.</h2><p>The application foundation connects the interface, API and database. Case management and evidence analysis will follow in reviewed development phases.</p><a href="#system" className="hero-link">View system connections <span aria-hidden="true">↗</span></a></div><div className="hero-emblem" aria-hidden="true"><span>§</span><small>INTEGRITY · CONTEXT · REVIEW</small></div></section>
        <section id="system" aria-labelledby="system-title"><div className="section-heading"><div><h2 id="system-title">System connections</h2><p>Live checks from the application, without sample case data.</p></div><button onClick={() => void refresh()} disabled={loading} className="refresh">{loading ? "Checking…" : "↻ Refresh status"}</button></div>
          <div className="status-grid" aria-live="polite" aria-busy={loading}>
            <article className="status-card"><span className="card-icon" aria-hidden="true">⌘</span><h3>Frontend</h3><p>Next.js · App Router</p><span className="status good">Page loaded</span></article>
            <article className="status-card"><span className="card-icon" aria-hidden="true">⇄</span><h3>API & readiness</h3><p>FastAPI · REST</p><span className={`status ${connected ? "good" : "pending"}`}>{loading ? "Checking" : connected ? "Ready" : "Unavailable / not ready"}</span></article>
            <article className="status-card"><span className="card-icon" aria-hidden="true">▤</span><h3>Database</h3><p>PostgreSQL · Alembic</p><span className={`status ${connected ? "good" : "pending"}`}>{loading ? "Checking" : connected ? "Connected & migrated" : "Connection unverified"}</span></article>
          </div>
          <p className="check-note">{checkedAt ? `Last checked at ${checkedAt}.` : "Checking application readiness."} {!loading && !connected && "Start the backend and apply the database migration, then refresh."}</p>
        </section>
        <div className="lower-grid"><section className="panel"><span className="eyebrow">YOUR WORKSPACE</span><h2>Ready for the next phase</h2><div className="empty-symbol" aria-hidden="true">▱</div><h3>No case data is available yet</h3><p>Case records, evidence counts and activity will appear after the database schema and authorized case workflows are implemented.</p><span className="outline-tag">No evidence or datasets imported</span></section>
        <section className="panel roadmap"><span className="eyebrow">WHAT COMES NEXT</span><h2>A measured path forward</h2>{modules.map(([phase, title, text]) => <div className="roadmap-row" key={phase}><span>{phase}</span><div><h3>{title}</h3><p>{text}</p></div></div>)}</section></div>
        <footer><span>AI Legal Evidence Analysis System</span><span>Decision support · Qualified human review required</span></footer>
      </main>
    </div>
  </div>;
}
