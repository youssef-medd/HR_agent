import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { API_URL, SESSION_COOKIE } from "@/lib/api/client";

/** A2 — update a sourced person (mark contacted, notes). */
export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ sourcedId: string }> },
) {
  const jar = await cookies();
  const t = jar.get(SESSION_COOKIE)?.value;
  if (!t) return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  const { sourcedId } = await params;
  const body = await request.text();
  const upstream = await fetch(`${API_URL}/jobs/sourced/${sourcedId}`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${t}`, "Content-Type": "application/json" },
    body,
    cache: "no-store",
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}
