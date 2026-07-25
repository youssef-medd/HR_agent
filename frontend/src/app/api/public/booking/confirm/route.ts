import { NextResponse } from "next/server";

import { API_URL } from "@/lib/api/client";

/** Public A6 booking confirm — proxies POST /public/booking/confirm. No session. */
export async function POST(request: Request) {
  const body = await request.text();
  const upstream = await fetch(`${API_URL}/public/booking/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    cache: "no-store",
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}
