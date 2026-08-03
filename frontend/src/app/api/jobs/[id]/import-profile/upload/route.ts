import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { API_URL, SESSION_COOKIE } from "@/lib/api/client";

/** A2 — upload an exported profile (PDF/DOCX/TXT) as a scored application. */
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const jar = await cookies();
  const t = jar.get(SESSION_COOKIE)?.value;
  if (!t) return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  const { id } = await params;
  const form = await request.formData();
  const upstream = await fetch(`${API_URL}/jobs/${id}/import-profile/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${t}` },
    body: form,
    cache: "no-store",
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}
