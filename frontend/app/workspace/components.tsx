"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { FormEvent, ReactNode, useCallback, useEffect, useState } from "react";
import { api, ApiError, jsonApi } from "./api";
import { EvidenceAnalysis } from "./analysis";
import { VisualAnalysis } from "./visual";
import { CaseReports } from "./reports";
import { CaseResearch } from "./research";
import "./workspace.css";

type User = { id: string; email: string; display_name: string; role: string };
type Case = { id: string; reference: string; title: string; description: string; jurisdiction: string; status: string; owner_id: string; opened_on: string; incident_on: string | null; created_at: string; can_write: boolean; can_manage: boolean };
type Evidence = { id: string; original_filename: string; mime_type: string; byte_size: number; sha256: string; provenance: string; uploader_id: string; created_at: string };
const message = (error: unknown) => error instanceof Error ? error.message : "Request failed";

export function Icon({ name }: { name: string }) {
  const paths: Record<string,string> = {
    dashboard: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
    cases: "M3 7h7l2 2h9v11H3z M3 7V4h7l2 3",
    plus: "M12 5v14 M5 12h14",
    research: "M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16 M16 16l6 6",
    account: "M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M4 21v-3a8 8 0 0 1 16 0v3",
    evidence: "M6 2h8l4 4v16H6z M14 2v5h5 M9 12h6 M9 16h6",
    shield: "M12 2l8 4v6c0 5-8 10-8 10S4 17 4 12V6z M8 12l3 3 5-6",
  };
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] ?? paths.evidence}/></svg>;
}

export function Frame({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const items = [["/","dashboard","Overview"],["/cases","cases","Cases"],["/cases/new","plus","Create case"],["/research","research","Legal research"]];
  const inCase = /^\/cases\/[^/]+$/.test(pathname) && pathname !== "/cases/new";
  const title = pathname === "/" ? "Overview" : pathname === "/research" ? "Legal research" : pathname === "/login" ? "Sign in" : pathname === "/register" ? "Create account" : inCase ? "Case workspace" : "Case management";
  return <div className="platform-shell"><a className="skip-link" href="#workspace-content">Skip to content</a><aside className="platform-sidebar"><Link className="platform-brand" href="/"><span className="brand-icon"><Icon name="shield"/></span><span>LEXISCOPE<small>Legal Investigation Intelligence</small></span></Link><p className="nav-caption">WORKSPACE</p><nav aria-label="Primary navigation">{items.map(([href,icon,label]) => { const active = href === "/cases" ? pathname === href || inCase : pathname === href; return <Link key={href} href={href} aria-current={active ? "page" : undefined}><Icon name={icon}/>{label}</Link>; })}</nav>{inCase && <><p className="nav-caption">THIS CASE</p><nav aria-label="Case navigation"><a href="#case-evidence"><Icon name="evidence"/>Evidence & analysis</a><a href="#case-research"><Icon name="research"/>Case research</a><a href="#case-reports"><Icon name="evidence"/>Investigation reports</a></nav></>}<div className="sidebar-bottom"><nav aria-label="Account navigation"><Link href="/login" aria-current={pathname === "/login" ? "page" : undefined}><Icon name="account"/>Sign in</Link><Link href="/register" aria-current={pathname === "/register" ? "page" : undefined}><Icon name="plus"/>Create account</Link></nav><p><Icon name="shield"/>Private by design</p><small>Authorized case access | Local processing</small></div></aside><div className="platform-main"><header className="platform-header"><span>Workspace <span className="breadcrumb-divider">/</span> <strong>{title}</strong></span><span className="local-label">Local workspace</span></header><main id="workspace-content" className="secure-workspace"><div className="legal-notice"><Icon name="shield"/><span>Verified statutory recommendations are currently unavailable. Automated observations require human review.</span></div>{children}<footer className="platform-footer"><span>LEXISCOPE | Legal Investigation Intelligence</span><span>Source grounded. Human review required.</span></footer></main></div></div>;
}

function useUser() {
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");
  const router = useRouter();
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        let result;
        try { result = await jsonApi("/auth/me"); }
        catch (e) { if (!(e instanceof ApiError) || e.status !== 401) throw e; await jsonApi("/auth/refresh", "POST"); result = await jsonApi("/auth/me"); }
        if (active) setUser(result);
      } catch (e) { if (active) { if (e instanceof ApiError && e.status === 401) router.replace("/login"); else setError(message(e)); } }
    })();
    return () => { active = false; };
  }, [router]);
  return { user, error };
}

function Identity({ user }: { user: User }) {
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return <div className="identity"><span>{user.display_name} · {user.role.replaceAll("_", " ")}</span><button disabled={busy} onClick={async () => {
    setBusy(true); setError(""); try { await jsonApi("/auth/logout", "POST"); router.replace("/login"); router.refresh(); } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }}>{busy ? "Logging out…" : "Logout"}</button>{error && <p role="alert">{error}</p>}</div>;
}

export function AuthPage({ register = false }: { register?: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [success, setSuccess] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setSuccess("");
    const element = event.currentTarget, form = new FormData(element);
    try {
      const body = { email: form.get("email"), password: form.get("password"), ...(register ? { display_name: form.get("display_name") } : {}) };
      await jsonApi(register ? "/auth/register" : "/auth/login", "POST", body);
      if (register) { element.reset(); setSuccess("Registration saved. Log in to open your workspace."); }
      else { router.replace("/cases"); router.refresh(); }
    } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }
  return <Frame><div className="auth-layout"><aside className="auth-intro"><span className="eyebrow">SECURE INVESTIGATION WORKSPACE</span><h2>Every source connected.<br/>Human review at the center.</h2><p>Bring case records, private evidence and local AI observations together in one traceable workflow.</p><ul><li>Case-level access controls</li><li>Original files preserved with SHA-256</li><li>Source-linked research and reviewed reports</li></ul></aside><div className="auth-panel"><span className="eyebrow">YOUR WORKSPACE</span><h1>{register ? "Create your account" : "Welcome back"}</h1><p>{register ? "Create a legal researcher account. You can manage your own cases. Access to another person's case requires an invitation." : "Sign in to access your private cases and evidence."}</p>
    <form onSubmit={submit}>{register && <label>Display name<input name="display_name" required maxLength={100} autoComplete="name" /></label>}
      <label>Email<input type="email" name="email" required maxLength={254} autoComplete="email" /></label>
      <label>Password<input type="password" name="password" required minLength={register ? 12 : 1} maxLength={128} autoComplete={register ? "new-password" : "current-password"} /></label>
      {register && <small>Use at least 12 characters and a varied passphrase.</small>}
      <button disabled={busy}>{busy ? "Saving…" : register ? "Register" : "Login"}</button></form>
    {error && <p role="alert" className="error">{error}</p>}{success && <p role="status">{success} <Link href="/login">Login</Link></p>}<p>{register ? "Already registered?" : "New to the platform?"} <Link href={register ? "/login" : "/register"}>{register ? "Sign in" : "Create an account"}</Link></p></div></div>
  </Frame>;
}

export function CaseList() {
  const { user, error: authError } = useUser();
  const [rows, setRows] = useState<Case[]>([]), [error, setError] = useState(""), [loading, setLoading] = useState(true);
  const [q, setQ] = useState(""), [status, setStatus] = useState(""), [offset, setOffset] = useState(0), [total, setTotal] = useState(0);
  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true); setError("");
    try { const result = await jsonApi(`/cases?${new URLSearchParams({ q, offset: String(offset), ...(status ? { status } : {}) })}`); setRows(result.items); setTotal(result.total); }
    catch (e) { setRows([]); setError(message(e)); } finally { setLoading(false); }
  }, [user, q, status, offset]);
  useEffect(() => { void load(); }, [load]);
  return <Frame><div className="page-title"><div><span className="eyebrow">CASE MANAGEMENT</span><h1>Cases</h1><p>Organize your investigations and open a secure case workspace.</p></div><Link className="button-link" href="/cases/new"><Icon name="plus"/>Create case</Link></div>{user && <Identity user={user} />}{authError && <p role="alert">{authError}</p>}
    <div className="filter-bar"><label>Search by title, reference or description<input value={q} onChange={e => { setQ(e.target.value); setOffset(0); }} maxLength={200} /></label>
    <label>Status<select value={status} onChange={e => { setStatus(e.target.value); setOffset(0); }}><option value="">All</option><option value="active">Active</option><option value="archived">Archived</option></select></label></div>
    {loading ? <p role="status">Loading cases…</p> : error ? <p role="alert">{error} <button onClick={() => void load()}>Retry</button></p> : !rows.length ? <p>No cases match. <Link href="/cases/new">Create your first case</Link>.</p> : <ul className="case-list case-grid">{rows.map(row => <li key={row.id}><div className="case-card-heading"><Icon name="cases"/><Link href={`/cases/${row.id}`}>{row.title}</Link><span className="status-badge">{row.status}</span></div><p>{row.reference} · {row.jurisdiction} · {row.status}</p></li>)}</ul>}
    <div className="actions"><button disabled={offset === 0 || loading} onClick={() => setOffset(offset-20)}>Previous</button><span>{total} cases</span><button disabled={offset+20 >= total || loading} onClick={() => setOffset(offset+20)}>Next</button></div>
  </Frame>;
}

function CaseInputs({ row }: { row?: Case }) {
  return <><label>Title<input name="title" defaultValue={row?.title} required maxLength={300} /></label><label>Description<textarea name="description" defaultValue={row?.description} maxLength={10000} /></label>
    <label>Jurisdiction<input name="jurisdiction" defaultValue={row?.jurisdiction} required maxLength={255} /></label>
    <label>Opened date<input type="date" name="opened_on" defaultValue={row?.opened_on ?? new Date().toLocaleDateString("en-CA")} required /></label>
    <label>Incident date (optional)<input type="date" name="incident_on" defaultValue={row?.incident_on ?? ""} /></label></>;
}

function caseBody(form: FormData) {
  return { title: form.get("title"), description: form.get("description"), jurisdiction: form.get("jurisdiction"), opened_on: form.get("opened_on"), incident_on: form.get("incident_on") || null };
}

export function NewCase() {
  const { user, error: authError } = useUser(); const router = useRouter();
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  return <Frame><span className="eyebrow">NEW INVESTIGATION</span><h1>Create case</h1><p>Start with case metadata, then add authorized evidence and analysis.</p>{user && <Identity user={user} />}{authError && <p role="alert">{authError}</p>}
    {user ? <form onSubmit={async e => { e.preventDefault(); const data = new FormData(e.currentTarget); setBusy(true); setError(""); try { const row = await jsonApi("/cases", "POST", caseBody(data)); router.push(`/cases/${row.id}`); } catch (e) { setError(message(e)); } finally { setBusy(false); } }}><CaseInputs /><button disabled={busy}>{busy ? "Creating…" : "Create case"}</button></form> : <p>Checking session…</p>}{error && <p role="alert">{error}</p>}
  </Frame>;
}

export function CaseDetail({ id }: { id: string }) {
  const { user, error: authError } = useUser();
  const [row, setRow] = useState<Case | null>(null), [evidence, setEvidence] = useState<Evidence[]>([]), [total, setTotal] = useState(0), [offset, setOffset] = useState(0);
  const [error, setError] = useState(""), [notice, setNotice] = useState(""), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [maxBytes, setMaxBytes] = useState<number | null>(null);
  const [members, setMembers] = useState<User[]>([]), [activity, setActivity] = useState<{ id: string; action: string; actor: string; created_at: string }[]>([]);
  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true); setError("");
    try {
      const [record, files, settings] = await Promise.all([jsonApi(`/cases/${id}`), jsonApi(`/cases/${id}/evidence?offset=${offset}`), jsonApi("/workspace/settings")]);
      setRow(record); setEvidence(files.items); setTotal(files.total); setMaxBytes(settings.max_file_bytes);
      if (record.can_manage) { const [m, a] = await Promise.all([jsonApi(`/cases/${id}/members`), jsonApi(`/cases/${id}/audit`)]); setMembers(m.items); setActivity(a.items); }
    } catch (e) { setRow(null); setEvidence([]); setMembers([]); setActivity([]); setError(message(e)); } finally { setLoading(false); }
  }, [user, id, offset]);
  useEffect(() => { void load(); }, [load]);
  async function action(work: () => Promise<void>) { setBusy(true); setError(""); setNotice(""); try { await work(); } catch (e) { setError(message(e)); } finally { setBusy(false); } }
  return <Frame><h1>{row?.title ?? "Case details"}</h1>{user && <Identity user={user} />}{authError && <p role="alert">{authError}</p>}{error && <p role="alert" className="error">{error} <button onClick={() => void load()}>Retry</button></p>}{notice && <p role="status">{notice}</p>}
    {loading && <p role="status">Loading case…</p>}{row && <><p>{row.reference} · {row.status} · Owner: {row.owner_id}</p>
      <nav className="case-tabs" aria-label="Case workflow"><a href="#case-overview">Overview</a><a href="#case-evidence">Evidence & AI analysis</a><a href="#case-research">Legal research</a><a href="#case-reports">Reports & review</a><a href="#case-access">Access & audit</a></nav><section id="case-overview"><h2>Case overview</h2>{row.can_write ? <form key={row.id+row.title+row.description} onSubmit={e => { e.preventDefault(); const data = new FormData(e.currentTarget); void action(async () => { await jsonApi(`/cases/${id}`, "PATCH", caseBody(data)); await load(); setNotice("Case saved."); }); }}><CaseInputs row={row} /><button disabled={busy}>Save changes</button></form> : <section><p>{row.description || "No description supplied."}</p><p>Jurisdiction: {row.jurisdiction}</p><p>Opened: {row.opened_on}; incident: {row.incident_on || "Not supplied"}</p><p>This case is read-only for your account.</p></section>}
      {row.can_manage && row.status === "active" && <button disabled={busy} onClick={() => { if (window.confirm("Archive this case? Evidence will remain available and the case will become read-only.")) void action(async () => { await jsonApi(`/cases/${id}/archive`, "POST"); await load(); }); }}>Archive case</button>}
      </section><section id="case-evidence" aria-label="Case evidence"><h2>Evidence library</h2><p>Originals are preserved unchanged. Downloads require current case access.</p>
      {row.can_write && <form onSubmit={e => { e.preventDefault(); const element = e.currentTarget, form = new FormData(element), file = form.get("file") as File; void action(async () => {
        if (!file?.size || (maxBytes !== null && file.size > maxBytes)) throw new Error("Select a non-empty file within the displayed size limit.");
        const sha = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await file.arrayBuffer()))).map(v => v.toString(16).padStart(2, "0")).join("");
        const params = new URLSearchParams({ filename: file.name, provenance: String(form.get("provenance")), ...(form.get("captured_on") ? { captured_on: String(form.get("captured_on")) } : {}) });
        const stored = await (await api(`/cases/${id}/evidence?${params}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file })).json();
        if (stored.sha256 !== sha) throw new Error("Uploaded hash differs from the selected file. Contact the operator.");
        element.reset(); await load(); setNotice(`Original saved; SHA-256 verified: ${sha}`);
      }); }}><label>Original PDF, PNG, JPG, JPEG or MP4<input type="file" name="file" accept=".pdf,.png,.jpg,.jpeg,.mp4" required /></label><small>{maxBytes === null ? "Loading upload limit…" : `Maximum ${maxBytes.toLocaleString()} bytes. Video validation has bounded duration and resolution.`}</small>
        <label>Provenance / authorized source<textarea name="provenance" required minLength={3} maxLength={2000} /></label><label>Captured date (optional)<input name="captured_on" type="date" /></label><button disabled={busy || maxBytes === null}>{busy ? "Working…" : "Upload and verify SHA-256"}</button></form>}
      {!evidence.length ? <p>No evidence uploaded.</p> : <ul className="case-list">{evidence.map(file => <li key={file.id}><div className="case-card-heading"><Icon name="evidence"/><strong>{file.original_filename}</strong><span className="status-badge">{file.mime_type.split("/")[1]}</span></div><p>{file.mime_type} · {file.byte_size.toLocaleString()} bytes · {new Date(file.created_at).toLocaleString()}</p><p>{file.provenance}</p><code>{file.sha256}</code><p>Uploader: {file.uploader_id}</p><button disabled={busy} onClick={() => void action(async () => {
        const response = await api(`/cases/${id}/evidence/${file.id}/download`), blob = await response.blob();
        const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await blob.arrayBuffer()))).map(v => v.toString(16).padStart(2, "0")).join("");
        if (hash !== file.sha256) throw new Error("Downloaded original failed SHA-256 verification");
        const url = URL.createObjectURL(blob), link = document.createElement("a"); link.href = url; link.download = file.original_filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 10000); setNotice("Download SHA-256 verified.");
      })}>Download verified original</button><EvidenceAnalysis caseId={id} evidenceId={file.id} mime={file.mime_type} canWrite={row.can_write} /><VisualAnalysis caseId={id} evidenceId={file.id} mime={file.mime_type} canWrite={row.can_write} /></li>)}</ul>}
      <div className="actions"><button disabled={!offset || busy} onClick={() => setOffset(offset-20)}>Previous</button><span>{total} files</span><button disabled={offset+20 >= total || busy} onClick={() => setOffset(offset+20)}>Next</button></div>
      </section><div id="case-research"><CaseResearch caseId={id} canInitiate={row.can_write && !!user && ["administrator","investigator","lawyer"].includes(user.role)} /></div><div id="case-reports"><CaseReports caseId={id} canGenerate={row.can_write && !!user && ["administrator","investigator","lawyer"].includes(user.role)} canApprove={row.can_write && !!user && ["administrator","lawyer"].includes(user.role)} /></div><section id="case-access"><h2>Access & audit</h2>{!row.can_manage && <p>Case ownership or administrator permission is required to manage access and inspect the case audit.</p>}
      {row.can_manage && <><h3>Case access</h3><p>Assigned investigators and lawyers can edit active cases. Assigned legal researchers have read-only access. Owners manage their own cases.</p>{row.status === "active" && <form onSubmit={e => { e.preventDefault(); const form = new FormData(e.currentTarget); void action(async () => { await jsonApi(`/cases/${id}/members`, "POST", { email: form.get("email") }); await load(); setNotice("Case access granted."); }); }}><label>Registered collaborator email<input type="email" name="email" required /></label><button disabled={busy}>Grant case access</button></form>}
        <ul>{members.map(m => <li key={m.id}>{m.display_name} ({m.email}) · {m.role} <button disabled={busy} onClick={() => void action(async () => { await jsonApi(`/cases/${id}/members/${m.id}`, "DELETE"); await load(); })}>Revoke access</button></li>)}</ul>
        <h2>Recent case audit</h2><ul>{activity.map(a => <li key={a.id}>{new Date(a.created_at).toLocaleString()} · {a.action} · {a.actor}</li>)}</ul></>}
    </section></>}
  </Frame>;
}
