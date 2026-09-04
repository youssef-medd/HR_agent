import { NextResponse } from "next/server";

import { API_URL } from "@/lib/api/client";

/**
 * Reads contact details out of a dropped CV so the apply form fills itself.
 * Proxies POST /public/prefill. No session, nothing stored.
 *
 * Any failure returns empty fields rather than an error — the candidate can
 * always type the details, and a bad parse must never block an application.
 */
export async function POST(request: Request) {
  const empty = { full_name: "", email: "", phone: "", link: "" };
  try {
    const form = await request.formData();
    const upstream = await fetch(`${API_URL}/public/prefill`, {
      method: "POST",
      body: form,
      cache: "no-store",
    });
    if (!upstream.ok) return NextResponse.json(empty);
    return NextResponse.json(await upstream.json());
  } catch {
    return NextResponse.json(empty);
  }
}
