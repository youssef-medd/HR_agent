import { NextResponse } from "next/server";

import { API_URL } from "@/lib/api/client";

/** Public candidate apply — forwards the multipart CV to FastAPI POST /public/apply.
 *  No session: this is the only unauthenticated BFF proxy. */
export async function POST(request: Request) {
  // Re-send the incoming multipart form as-is. Do NOT set Content-Type —
  // fetch derives the multipart boundary from the FormData body.
  const form = await request.formData();

  const upstream = await fetch(`${API_URL}/public/apply`, {
    method: "POST",
    body: form,
    cache: "no-store",
  });

  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}
