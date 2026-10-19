import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  const base = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${base}/api/v1/health/ready`, {
      cache: "no-store", signal: AbortSignal.timeout(5000),
    });
    const data = await response.json();
    if (!response.ok || data.status !== "ok" || data.database !== "connected") {
      return NextResponse.json({ status: "unavailable", database: "unavailable" }, { status: 503 });
    }
    return NextResponse.json({ status: "ok", database: "connected", migration: data.migration });
  } catch {
    return NextResponse.json({ status: "unavailable", database: "unavailable" }, { status: 503 });
  }
}
