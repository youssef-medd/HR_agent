import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { API_URL, SESSION_COOKIE } from "@/lib/api/client";

/** Forwards a recruiter gate decision to FastAPI POST /needs-attention/{id}/resolve. */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  const { id } = await params;
  const upstream = await fetch(`${API_URL}/needs-attention/${id}/resolve`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}
