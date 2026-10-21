import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if (!path.length || !["auth", "cases", "admin", "workspace", "research"].includes(path[0]) || path.some(p => !/^[A-Za-z0-9_-]+$/.test(p))) {
    return NextResponse.json({ detail: "Route not found" }, { status: 404 });
  }
  const mutating = !["GET", "HEAD"].includes(request.method);
  const origin = request.headers.get("origin");
  if (mutating && origin && new URL(origin).host !== request.headers.get("host")) {
    return NextResponse.json({ detail: "Request origin rejected" }, { status: 403 });
  }
  const headers = new Headers();
  for (const name of ["content-type", "cookie", "x-csrf-token", "origin", "content-length"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  try {
    const base = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
    const init: RequestInit & { duplex?: "half" } = {
      method: request.method, headers, cache: "no-store", redirect: "manual", signal: AbortSignal.timeout(90000),
    };
    if (mutating && request.body) { init.body = request.body; init.duplex = "half"; }
    const upstream = await fetch(`${base}/api/v1/${path.join("/")}${request.nextUrl.search}`, init);
    const output = new Headers({ "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" });
    for (const name of ["content-type", "content-disposition", "content-security-policy", "x-content-sha256", "retry-after"]) {
      const value = upstream.headers.get(name);
      if (value) output.set(name, value);
    }
    for (const value of upstream.headers.getSetCookie()) output.append("Set-Cookie", value);
    return new NextResponse(upstream.body, { status: upstream.status, headers: output });
  } catch {
    return NextResponse.json({ detail: "Backend unavailable or request timed out" }, { status: 503 });
  }
}

export { proxy as GET, proxy as POST, proxy as PATCH, proxy as DELETE };
