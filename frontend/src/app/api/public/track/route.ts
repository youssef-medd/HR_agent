import { NextResponse } from "next/server";

import { API_URL } from "@/lib/api/client";

/**
 * Public candidate tracking — proxies GET /public/track. No session.
 *
 * Accepts either a signed portal token (`t`) or the legacy email + reference
 * pair, and forwards whichever was given.
 */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const token = searchParams.get("t");

  const query = token
    ? `token=${encodeURIComponent(token)}`
    : `email=${encodeURIComponent(searchParams.get("email") ?? "")}` +
      `&application_id=${encodeURIComponent(searchParams.get("application_id") ?? "")}`;

  const upstream = await fetch(`${API_URL}/public/track?${query}`, {
    cache: "no-store",
  });

  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}
