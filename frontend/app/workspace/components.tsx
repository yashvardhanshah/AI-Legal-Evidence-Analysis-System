"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { FormEvent, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, jsonApi } from "./api";
import { EvidenceAnalysis } from "./analysis";
import { VisualAnalysis } from "./visual";
import { CaseReports } from "./reports";
import { CaseResearch } from "./research";
import { ArchiveButton, EmptyState, Glyph, Loading, SourceArtwork, StatusBadge, UploadField } from "./ui";
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
  const mobileNav = useRef<HTMLDialogElement>(null);
  const router = useRouter();
  const [identity, setIdentity] = useState<User | null>(null);
  const [sessionError, setSessionError] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);
  useEffect(() => { let current = true; jsonApi("/auth/me").then(value => { if (current) setIdentity(value); }).catch(() => { if (current) setIdentity(null); }); return () => { current = false; }; }, [pathname]);
  useEffect(() => { mobileNav.current?.close(); }, [pathname]);
  const navigation = <><Link className="platform-brand" href="/"><span className="brand-icon"><Icon name="shield"/></span><span>LEXISCOPE<small>Legal Investigation Intelligence</small></span></Link><p className="nav-caption">INVESTIGATION</p><nav aria-label="Primary navigation">{items.map(([href,icon,label]) => { const active = href === "/cases" ? pathname === href || inCase : pathname === href; return <Link key={href} href={href} aria-current={active ? "page" : undefined}><Icon name={icon}/>{label}</Link>; })}</nav>{inCase && <><p className="nav-caption">CASE TOOLS</p><nav aria-label="Case navigation" onClick={() => mobileNav.current?.close()}><a href="#case-evidence"><Icon name="evidence"/>Evidence & analysis</a><a href="#case-research"><Icon name="research"/>Case research</a><a href="#case-reports"><Icon name="evidence"/>Investigation reports</a></nav></>}<div className="sidebar-bottom"><div className="sidebar-note"><Icon name="shield"/><strong>Local intelligence.<br/>Traceable sources.</strong><p>Original evidence preserved.<br/>Human review required.</p></div><nav aria-label="Account navigation">{identity ? <><Link href="/cases"><Icon name="account"/>{identity.display_name}</Link><button className="sidebar-logout" disabled={loggingOut} onClick={async () => { setLoggingOut(true); setSessionError(""); try { await jsonApi("/auth/logout", "POST"); setIdentity(null); mobileNav.current?.close(); router.replace("/login"); router.refresh(); } catch (e) { setSessionError(message(e)); } finally { setLoggingOut(false); } }}>{loggingOut ? "Logging out..." : "Logout"}</button></> : <><Link href="/login"><Icon name="account"/>Sign in</Link><Link href="/register"><Icon name="plus"/>Create account</Link></>}</nav><small>Local processing | Authorized access</small></div></>;
  return <div className="platform-shell"><a className="skip-link" href="#workspace-content">Skip to content</a><aside className="platform-sidebar">{navigation}</aside><dialog ref={mobileNav} className="mobile-nav" aria-label="Workspace navigation"><button className="nav-close" aria-label="Close navigation" onClick={() => mobileNav.current?.close()}><Glyph name="close"/></button>{navigation}</dialog><div className="platform-main"><header className="platform-header"><div className="header-location"><button className="nav-toggle" aria-label="Open navigation" aria-haspopup="dialog" onClick={() => mobileNav.current?.showModal()}><Glyph name="menu"/></button><nav aria-label="Breadcrumb"><Link href="/">Workspace</Link><span className="breadcrumb-divider">/</span><strong>{title}</strong></nav></div><div className="header-account"><span className="local-label"><span className="local-dot"/>Local workspace</span>{identity && <Link className="avatar" href="/cases" aria-label={`Cases for ${identity.display_name}`}>{identity.display_name.slice(0, 2).toUpperCase()}</Link>}</div></header><main id="workspace-content" className="secure-workspace"><div className="legal-notice"><Icon name="shield"/><span>Verified statutory recommendations are currently unavailable. Automated observations require human review.</span></div>{sessionError && <p role="alert">{sessionError}</p>}{children}<footer className="platform-footer"><span>LEXISCOPE | Legal Investigation Intelligence</span><span>Source grounded. Human review required.</span></footer></main></div></div>;
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
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [success, setSuccess] = useState(""), [showPassword, setShowPassword] = useState(false);
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
  return <Frame><div className="auth-layout"><aside className="auth-intro"><span className="eyebrow">SECURE INVESTIGATION WORKSPACE</span><h2>Every source connected.<br/>Human review at the center.</h2><p>Bring case records, private evidence and local AI observations together in one traceable workflow.</p><SourceArtwork/><ul><li>Case-level access controls</li><li>Original files preserved with SHA-256</li><li>Source-linked research and reviewed reports</li></ul></aside><div className="auth-panel"><span className="eyebrow">YOUR WORKSPACE</span><h1>{register ? "Create your account" : "Welcome back"}</h1><p>{register ? "Create a legal researcher account. You can manage your own cases. Access to another person's case requires an invitation." : "Sign in to access your private cases and evidence."}</p>
    <form onSubmit={submit}>{register && <label>Display name<input name="display_name" required maxLength={100} autoComplete="name" /></label>}
      <label>Email<input type="email" name="email" required maxLength={254} autoComplete="email" /></label>
      <label htmlFor="auth-password">Password</label><div className="password-field"><input id="auth-password" type={showPassword ? "text" : "password"} name="password" required minLength={register ? 12 : 1} maxLength={128} autoComplete={register ? "new-password" : "current-password"} aria-describedby={register ? "password-help" : undefined}/><button type="button" className="password-toggle" aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}><Glyph name="eye"/></button></div>
      {register && <small id="password-help">Use at least 12 characters and a varied passphrase.</small>}
      <button type="submit" disabled={busy}>{busy ? "Saving…" : register ? "Register" : "Login"}</button></form>
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
    {loading ? <Loading label="Loading authorized cases"/> : error ? <p role="alert">{error} <button onClick={() => void load()}>Retry</button></p> : !rows.length ? <EmptyState title="No matching cases" text="Create a case or adjust your search and status filter." icon="layers"/> : <ul className="case-list case-grid">{rows.map(row => <li key={row.id}><div className="case-card-heading"><Icon name="cases"/><Link href={`/cases/${row.id}`}>{row.title}</Link><StatusBadge status={row.status}/></div><p className="case-reference">{row.reference}</p><p>{row.description || "No case description supplied."}</p><div className="case-card-meta"><span>{row.jurisdiction}</span><span>{row.owner_id === user?.id ? "Owned by you" : "Shared access"}</span></div></li>)}</ul>}
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
    {user ? <form className="case-create-form" onSubmit={async e => { e.preventDefault(); const data = new FormData(e.currentTarget); setBusy(true); setError(""); try { const row = await jsonApi("/cases", "POST", caseBody(data)); router.push(`/cases/${row.id}`); } catch (e) { setError(message(e)); } finally { setBusy(false); } }}><CaseInputs /><button disabled={busy}>{busy ? "Creating…" : "Create case"}</button></form> : <p>Checking session…</p>}{error && <p role="alert">{error}</p>}
  </Frame>;
}

export function CaseDetail({ id }: { id: string }) {
  const { user, error: authError } = useUser();
  const [row, setRow] = useState<Case | null>(null), [evidence, setEvidence] = useState<Evidence[]>([]), [total, setTotal] = useState(0), [offset, setOffset] = useState(0);
  const [error, setError] = useState(""), [notice, setNotice] = useState(""), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [maxBytes, setMaxBytes] = useState<number | null>(null);
  const [uploadStage, setUploadStage] = useState("");
  const [activeSection, setActiveSection] = useState("case-overview");
  useEffect(() => { const update = () => setActiveSection(location.hash.slice(1) || "case-overview"); update(); window.addEventListener("hashchange", update); return () => window.removeEventListener("hashchange", update); }, []);
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
  async function action(work: () => Promise<void>) { setBusy(true); setError(""); setNotice(""); try { await work(); } catch (e) { setUploadStage(""); setError(message(e)); } finally { setBusy(false); } }
  return <Frame><div className="case-workspace-heading"><span className="eyebrow">INVESTIGATION WORKSPACE</span><h1>{row?.title ?? "Case details"}</h1>{row && <div className="case-context"><StatusBadge status={row.status}/><span>{row.jurisdiction}</span><span>{row.owner_id === user?.id ? "Owned by you" : "Authorized shared access"}</span><span>{total} evidence files</span></div>}</div>{user && <Identity user={user} />}{authError && <p role="alert">{authError}</p>}{error && <p role="alert" className="error">{error} <button onClick={() => void load()}>Retry</button></p>}{notice && <p role="status">{notice}</p>}
    {loading && <Loading label="Loading case and evidence"/>}{row && <><p className="case-reference">{row.reference} <span>Owner: {row.owner_id}</span></p>
      <nav className="case-tabs" aria-label="Case workflow"><a href="#case-overview" aria-current={activeSection === "case-overview" ? "location" : undefined}>Overview</a><a href="#case-evidence" aria-current={activeSection === "case-evidence" ? "location" : undefined}>Evidence & AI analysis</a><a href="#case-research" aria-current={activeSection === "case-research" ? "location" : undefined}>Legal research</a><a href="#case-reports" aria-current={activeSection === "case-reports" ? "location" : undefined}>Reports & review</a><a href="#case-access" aria-current={activeSection === "case-access" ? "location" : undefined}>Access & audit</a></nav><section id="case-overview"><h2>Case overview</h2>{row.can_write ? <form key={row.id+row.title+row.description} onSubmit={e => { e.preventDefault(); const data = new FormData(e.currentTarget); void action(async () => { await jsonApi(`/cases/${id}`, "PATCH", caseBody(data)); await load(); setNotice("Case saved."); }); }}><CaseInputs row={row} /><button disabled={busy}>Save changes</button></form> : <section><p>{row.description || "No description supplied."}</p><p>Jurisdiction: {row.jurisdiction}</p><p>Opened: {row.opened_on}; incident: {row.incident_on || "Not supplied"}</p><p>This case is read-only for your account.</p></section>}
      {row.can_manage && row.status === "active" && <ArchiveButton disabled={busy} onConfirm={() => void action(async () => { await jsonApi(`/cases/${id}/archive`, "POST"); await load(); })}/>}
      </section><section id="case-evidence" aria-label="Case evidence"><h2>Evidence library</h2><p>Originals are preserved unchanged. Downloads require current case access.</p>
      {row.can_write && <form onSubmit={e => { e.preventDefault(); const element = e.currentTarget, form = new FormData(element), file = form.get("file") as File; void action(async () => {
        setUploadStage("Validating original file...");
        if (!file?.size || (maxBytes !== null && file.size > maxBytes)) throw new Error("Select a non-empty file within the displayed size limit.");
        setUploadStage("Calculating original SHA-256...");
        const sha = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await file.arrayBuffer()))).map(v => v.toString(16).padStart(2, "0")).join("");
        const params = new URLSearchParams({ filename: file.name, provenance: String(form.get("provenance")), ...(form.get("captured_on") ? { captured_on: String(form.get("captured_on")) } : {}) });
        setUploadStage("Uploading original; waiting for server validation...");
        const stored = await (await api(`/cases/${id}/evidence?${params}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file })).json();
        if (stored.sha256 !== sha) throw new Error("Uploaded hash differs from the selected file. Contact the operator.");
        element.reset(); setUploadStage("Original saved and SHA-256 verified."); await load(); setNotice(`Original saved; SHA-256 verified: ${sha}`);
      }); }}><UploadField disabled={busy}/>{uploadStage && <p role="status" className="upload-progress">{uploadStage}</p>}<small>{maxBytes === null ? "Loading upload limit…" : `Maximum ${maxBytes.toLocaleString()} bytes. Video validation has bounded duration and resolution.`}</small>
        <label>Provenance / authorized source<textarea name="provenance" required minLength={3} maxLength={2000} /></label><label>Captured date (optional)<input name="captured_on" type="date" /></label><button disabled={busy || maxBytes === null}>{busy ? "Working…" : "Upload and verify SHA-256"}</button></form>}
      {!evidence.length ? <EmptyState title="An evidence library with a clear chain of source" text="Upload an authorized original and record its provenance. Analysis never changes the original file." icon="upload"/> : <ul className="case-list">{evidence.map(file => <li key={file.id}><div className="case-card-heading"><Glyph name={file.mime_type === "video/mp4" ? "video" : file.mime_type.startsWith("image/") ? "image" : "document"}/><strong>{file.original_filename}</strong><span className="status-badge">{file.mime_type.split("/")[1]}</span></div><p>{file.mime_type} · {file.byte_size.toLocaleString()} bytes · {new Date(file.created_at).toLocaleString()}</p><p>{file.provenance}</p><code>{file.sha256}</code><details className="evidence-provenance"><summary>Source and integrity details</summary><p>Uploader: {file.uploader_id}</p><p>Original SHA-256: <code>{file.sha256}</code></p><p>{file.provenance}</p></details><button disabled={busy} onClick={() => void action(async () => {
        const response = await api(`/cases/${id}/evidence/${file.id}/download`), blob = await response.blob();
        const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await blob.arrayBuffer()))).map(v => v.toString(16).padStart(2, "0")).join("");
        if (hash !== file.sha256) throw new Error("Downloaded original failed SHA-256 verification");
        const url = URL.createObjectURL(blob), link = document.createElement("a"); link.href = url; link.download = file.original_filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 10000); setNotice("Download SHA-256 verified.");
      })}>Download verified original</button><EvidenceAnalysis caseId={id} evidenceId={file.id} mime={file.mime_type} canWrite={row.can_write} /><VisualAnalysis caseId={id} evidenceId={file.id} mime={file.mime_type} canWrite={row.can_write} /></li>)}</ul>}
      <div className="actions"><button disabled={!offset || busy} onClick={() => setOffset(offset-20)}>Previous</button><span>{total} files</span><button disabled={offset+20 >= total || busy} onClick={() => setOffset(offset+20)}>Next</button></div>
      </section><div id="case-research"><CaseResearch caseId={id} canInitiate={row.can_write && !!user && ["administrator","investigator","lawyer"].includes(user.role)} /></div><div id="case-reports"><CaseReports caseId={id} canGenerate={row.can_write && !!user && ["administrator","investigator","lawyer"].includes(user.role)} canApprove={row.can_write && !!user && ["administrator","lawyer"].includes(user.role)} /></div><section id="case-access"><h2>Access & audit</h2>{!row.can_manage && <p>Case ownership or administrator permission is required to manage access and inspect the case audit.</p>}
      {row.can_manage && <><h3>Case access</h3><p>Assigned investigators and lawyers can edit active cases. Assigned legal researchers have read-only access. Owners manage their own cases.</p>{row.status === "active" && <form onSubmit={e => { e.preventDefault(); const form = new FormData(e.currentTarget); void action(async () => { await jsonApi(`/cases/${id}/members`, "POST", { email: form.get("email") }); await load(); setNotice("Case access granted."); }); }}><label>Registered collaborator email<input type="email" name="email" required /></label><button disabled={busy}>Grant case access</button></form>}
        <ul>{members.map(m => <li key={m.id}>{m.display_name} ({m.email}) · {m.role} <button disabled={busy} onClick={() => void action(async () => { await jsonApi(`/cases/${id}/members/${m.id}`, "DELETE"); await load(); })}>Revoke access</button></li>)}</ul>
        <h2>Recent case audit</h2><ul className="activity-list">{activity.map(a => <li key={a.id}>{new Date(a.created_at).toLocaleString()} · {a.action} · {a.actor}</li>)}</ul></>}
    </section></>}
  </Frame>;
}
