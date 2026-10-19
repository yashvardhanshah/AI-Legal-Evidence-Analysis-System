export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

const base = "/api/backend";
let refreshing: Promise<Response> | null = null;

function csrf() {
  return document.cookie.split("; ").find(v => v.startsWith("legal_csrf="))?.split("=").slice(1).join("=") ?? "";
}

export async function api(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  if (!csrf()) {
    const response = await fetch(`${base}/auth/csrf`, { cache: "no-store" });
    if (!response.ok) throw new ApiError(response.status, "Could not initialize secure session");
  }
  const headers = new Headers(init.headers);
  if (init.method && init.method !== "GET") headers.set("X-CSRF-Token", csrf());
  const response = await fetch(`${base}${path}`, { ...init, headers, cache: "no-store" });
  if (response.status === 401 && retry && !path.startsWith("/auth/")) {
    if (!refreshing) refreshing = api("/auth/refresh", { method: "POST" }, false).finally(() => { refreshing = null; });
    await refreshing;
    return api(path, init, false);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : Array.isArray(body.detail) ? body.detail.map((e: { msg: string }) => e.msg).join("; ") : "Request failed";
    throw new ApiError(response.status, detail);
  }
  return response;
}

export async function jsonApi(path: string, method = "GET", body?: unknown) {
  return (await api(path, { method, ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }) })).json();
}
