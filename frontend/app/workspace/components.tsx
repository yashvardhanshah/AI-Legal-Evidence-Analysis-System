"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, ReactNode, useCallback, useEffect, useState } from "react";
import { api, ApiError, jsonApi } from "./api";
import { EvidenceAnalysis } from "./analysis";
import "./workspace.css";

type User = { id: string; email: string; display_name: string; role: string };
type Case = { id: string; reference: string; title: string; description: string; jurisdiction: string; status: string; owner_id: string; opened_on: string; incident_on: string | null; created_at: string; can_write: boolean; can_manage: boolean };
type Evidence = { id: string; original_filename: string; mime_type: string; byte_size: number; sha256: string; provenance: string; uploader_id: string; created_at: string };
const message = (error: unknown) => error instanceof Error ? error.message : "Request failed";

export function Frame({ children }: { children: ReactNode }) {
  return <main className="secure-workspace"><nav><Link href="/">System status</Link><Link href="/cases">Cases</Link><Link href="/cases/new">Create case</Link><Link href="/login">Login</Link><Link href="/register">Register</Link></nav>{children}</main>;
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
  return <Frame><h1>{register ? "Register" : "Login"}</h1><p>{register ? "Create a legal researcher account. You can manage your own cases. Access to another person's case requires an invitation." : "Sign in to access your private cases and evidence."}</p>
    <form onSubmit={submit}>{register && <label>Display name<input name="display_name" required maxLength={100} autoComplete="name" /></label>}
      <label>Email<input type="email" name="email" required maxLength={254} autoComplete="email" /></label>
      <label>Password<input type="password" name="password" required minLength={register ? 12 : 1} maxLength={128} autoComplete={register ? "new-password" : "current-password"} /></label>
      {register && <small>Use at least 12 characters and a varied passphrase.</small>}
      <button disabled={busy}>{busy ? "Saving…" : register ? "Register" : "Login"}</button></form>
    {error && <p role="alert" className="error">{error}</p>}{success && <p role="status">{success} <Link href="/login">Login</Link></p>}
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
  return <Frame><h1>Cases</h1>{user && <Identity user={user} />}{authError && <p role="alert">{authError}</p>}
    <label>Search by title, reference or description<input value={q} onChange={e => { setQ(e.target.value); setOffset(0); }} maxLength={200} /></label>
    <label>Status<select value={status} onChange={e => { setStatus(e.target.value); setOffset(0); }}><option value="">All</option><option value="active">Active</option><option value="archived">Archived</option></select></label>
    {loading ? <p role="status">Loading cases…</p> : error ? <p role="alert">{error} <button onClick={() => void load()}>Retry</button></p> : !rows.length ? <p>No cases match. <Link href="/cases/new">Create your first case</Link>.</p> : <ul className="case-list">{rows.map(row => <li key={row.id}><Link href={`/cases/${row.id}`}>{row.title}</Link><p>{row.reference} · {row.jurisdiction} · {row.status}</p></li>)}</ul>}
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
  return <Frame><h1>Create case</h1>{user && <Identity user={user} />}{authError && <p role="alert">{authError}</p>}
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
      {row.can_write ? <form key={row.id+row.title+row.description} onSubmit={e => { e.preventDefault(); const data = new FormData(e.currentTarget); void action(async () => { await jsonApi(`/cases/${id}`, "PATCH", caseBody(data)); await load(); setNotice("Case saved."); }); }}><CaseInputs row={row} /><button disabled={busy}>Save changes</button></form> : <section><p>{row.description || "No description supplied."}</p><p>Jurisdiction: {row.jurisdiction}</p><p>Opened: {row.opened_on}; incident: {row.incident_on || "Not supplied"}</p><p>This case is read-only for your account.</p></section>}
      {row.can_manage && row.status === "active" && <button disabled={busy} onClick={() => { if (window.confirm("Archive this case? Evidence will remain available and the case will become read-only.")) void action(async () => { await jsonApi(`/cases/${id}/archive`, "POST"); await load(); }); }}>Archive case</button>}
      <h2>Evidence</h2><p>Originals are preserved unchanged. Downloads require current case access.</p>
      {row.can_write && <form onSubmit={e => { e.preventDefault(); const element = e.currentTarget, form = new FormData(element), file = form.get("file") as File; void action(async () => {
        if (!file?.size || (maxBytes !== null && file.size > maxBytes)) throw new Error("Select a non-empty file within the displayed size limit.");
        const sha = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await file.arrayBuffer()))).map(v => v.toString(16).padStart(2, "0")).join("");
        const params = new URLSearchParams({ filename: file.name, provenance: String(form.get("provenance")), ...(form.get("captured_on") ? { captured_on: String(form.get("captured_on")) } : {}) });
        const stored = await (await api(`/cases/${id}/evidence?${params}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file })).json();
        if (stored.sha256 !== sha) throw new Error("Uploaded hash differs from the selected file. Contact the operator.");
        element.reset(); await load(); setNotice(`Original saved; SHA-256 verified: ${sha}`);
      }); }}><label>Original PDF, PNG, JPG, JPEG or MP4<input type="file" name="file" accept=".pdf,.png,.jpg,.jpeg,.mp4" required /></label><small>{maxBytes === null ? "Loading upload limit…" : `Maximum ${maxBytes.toLocaleString()} bytes. Video validation has bounded duration and resolution.`}</small>
        <label>Provenance / authorized source<textarea name="provenance" required minLength={3} maxLength={2000} /></label><label>Captured date (optional)<input name="captured_on" type="date" /></label><button disabled={busy || maxBytes === null}>{busy ? "Working…" : "Upload and verify SHA-256"}</button></form>}
      {!evidence.length ? <p>No evidence uploaded.</p> : <ul className="case-list">{evidence.map(file => <li key={file.id}><strong>{file.original_filename}</strong><p>{file.mime_type} · {file.byte_size.toLocaleString()} bytes · {new Date(file.created_at).toLocaleString()}</p><p>{file.provenance}</p><code>{file.sha256}</code><p>Uploader: {file.uploader_id}</p><button disabled={busy} onClick={() => void action(async () => {
        const response = await api(`/cases/${id}/evidence/${file.id}/download`), blob = await response.blob();
        const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await blob.arrayBuffer()))).map(v => v.toString(16).padStart(2, "0")).join("");
        if (hash !== file.sha256) throw new Error("Downloaded original failed SHA-256 verification");
        const url = URL.createObjectURL(blob), link = document.createElement("a"); link.href = url; link.download = file.original_filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 10000); setNotice("Download SHA-256 verified.");
      })}>Download verified original</button><EvidenceAnalysis caseId={id} evidenceId={file.id} mime={file.mime_type} canWrite={row.can_write} /></li>)}</ul>}
      <div className="actions"><button disabled={!offset || busy} onClick={() => setOffset(offset-20)}>Previous</button><span>{total} files</span><button disabled={offset+20 >= total || busy} onClick={() => setOffset(offset+20)}>Next</button></div>
      {row.can_manage && <><h2>Case access</h2><p>Assigned investigators and lawyers can edit active cases. Assigned legal researchers have read-only access. Owners manage their own cases.</p>{row.status === "active" && <form onSubmit={e => { e.preventDefault(); const form = new FormData(e.currentTarget); void action(async () => { await jsonApi(`/cases/${id}/members`, "POST", { email: form.get("email") }); await load(); setNotice("Case access granted."); }); }}><label>Registered collaborator email<input type="email" name="email" required /></label><button disabled={busy}>Grant case access</button></form>}
        <ul>{members.map(m => <li key={m.id}>{m.display_name} ({m.email}) · {m.role} <button disabled={busy} onClick={() => void action(async () => { await jsonApi(`/cases/${id}/members/${m.id}`, "DELETE"); await load(); })}>Revoke access</button></li>)}</ul>
        <h2>Recent case audit</h2><ul>{activity.map(a => <li key={a.id}>{new Date(a.created_at).toLocaleString()} · {a.action} · {a.actor}</li>)}</ul></>}
    </>}
  </Frame>;
}
