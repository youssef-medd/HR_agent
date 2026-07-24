import { NextResponse } from "next/server";

import { API_URL } from "@/lib/api/client";

/** Public A5 web-chat transcript — proxies GET /public/prescreen. No session. */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const email = searchParams.get("email") ?? "";
  const applicationId = searchParams.get("application_id") ?? "";

  const upstream = await fetch(
    `${API_URL}/public/prescreen?email=${encodeURIComponent(email)}&application_id=${encodeURIComponent(applicationId)}`,
    { cache: "no-store" },
  );
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}
