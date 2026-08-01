import { NextResponse } from "next/server";

import { API_URL } from "@/lib/api/client";

/** A8 candidate document upload — proxies POST /public/onboarding/upload (multipart). */
export async function POST(request: Request) {
  const form = await request.formData();
  const upstream = await fetch(`${API_URL}/public/onboarding/upload`, {
    method: "POST",
    body: form,
    cache: "no-store",
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}
