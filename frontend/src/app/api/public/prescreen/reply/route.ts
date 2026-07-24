import { NextResponse } from "next/server";

import { API_URL } from "@/lib/api/client";

/** Public A5 web-chat reply — proxies POST /public/prescreen/reply. No session. */
export async function POST(request: Request) {
  const body = await request.text();
  const upstream = await fetch(`${API_URL}/public/prescreen/reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    cache: "no-store",
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}
