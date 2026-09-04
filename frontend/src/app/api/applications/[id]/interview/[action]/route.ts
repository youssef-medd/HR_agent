import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { API_URL, SESSION_COOKIE } from "@/lib/api/client";

/** Whitelisted A6 recruiter actions on a booked interview. */
const ACTIONS = new Set(["reschedule", "no-show", "attended", "cancel"]);

/** Forwards to FastAPI POST /applications/{id}/interview/{action}. */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string; action: string }> },
) {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const { id, action } = await params;
  if (!ACTIONS.has(action)) {
    return NextResponse.json({ error: "Unknown interview action" }, { status: 404 });
  }

  const body = await request.text();
  const upstream = await fetch(`${API_URL}/applications/${id}/interview/${action}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body || undefined,
    cache: "no-store",
  });

  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}
