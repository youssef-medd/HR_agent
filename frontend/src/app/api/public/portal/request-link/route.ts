import { NextResponse } from "next/server";

import { API_URL } from "@/lib/api/client";

/**
 * "Email me my link" — proxies POST /public/portal/request-link. No session.
 *
 * Upstream always answers `sent: true` whether or not the address has applied,
 * so this route must not add any branch that would let a caller tell the
 * difference.
 */
export async function POST(request: Request) {
  let body: { email?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  if (!body.email) {
    return NextResponse.json({ error: "Email is required" }, { status: 400 });
  }

  try {
    const upstream = await fetch(`${API_URL}/public/portal/request-link`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: body.email }),
      cache: "no-store",
    });
    const data = await upstream.json().catch(() => ({}));
    return NextResponse.json(data, { status: upstream.status });
  } catch {
    return NextResponse.json({ error: "Service unreachable" }, { status: 502 });
  }
}
