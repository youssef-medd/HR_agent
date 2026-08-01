import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { API_URL, SESSION_COOKIE } from "@/lib/api/client";

async function token() {
  const jar = await cookies();
  return jar.get(SESSION_COOKIE)?.value;
}

/** A2 — list people sourced for this job. */
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const t = await token();
  if (!t) return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  const { id } = await params;
  const upstream = await fetch(`${API_URL}/jobs/${id}/sourced`, {
    headers: { Authorization: `Bearer ${t}` },
    cache: "no-store",
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}

/** A2 — record a sourced person (409 if already sourced for this job). */
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const t = await token();
  if (!t) return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  const { id } = await params;
  const body = await request.text();
  const upstream = await fetch(`${API_URL}/jobs/${id}/sourced`, {
    method: "POST",
    headers: { Authorization: `Bearer ${t}`, "Content-Type": "application/json" },
    body,
    cache: "no-store",
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}
