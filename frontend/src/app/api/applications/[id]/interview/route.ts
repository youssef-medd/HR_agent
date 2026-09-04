import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { API_URL, SESSION_COOKIE } from "@/lib/api/client";

/** Reads the A6 interview block — proxies GET /applications/{id}/interview. */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { id } = await params;
  const upstream = await fetch(`${API_URL}/applications/${id}/interview`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });

  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}
