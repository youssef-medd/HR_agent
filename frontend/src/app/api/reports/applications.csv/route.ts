import { cookies } from "next/headers";

import { API_URL, SESSION_COOKIE } from "@/lib/api/client";

/** A9 — proxy the CSV export, forwarding the recruiter session. */
export async function GET() {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) {
    return new Response("Not authenticated", { status: 401 });
  }
  const upstream = await fetch(`${API_URL}/reports/applications.csv`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/csv",
      "Content-Disposition": "attachment; filename=applications.csv",
    },
  });
}
