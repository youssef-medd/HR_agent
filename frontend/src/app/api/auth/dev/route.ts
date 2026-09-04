import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { API_URL, SESSION_COOKIE, type TokenResponse } from "@/lib/api/client";

const EIGHT_HOURS = 8 * 60 * 60;

/**
 * Development-only auto-login.
 *
 * Mints a session for the seeded admin so local work does not stop at the
 * login form. Gated twice: it is a no-op unless `DEV_AUTOLOGIN=1` AND the
 * build is not a production build, so it can never ship as an auth bypass.
 */
export async function GET(request: Request) {
  const enabled =
    process.env.DEV_AUTOLOGIN === "1" && process.env.NODE_ENV !== "production";
  if (!enabled) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const next = new URL(request.url).searchParams.get("next") || "/";
  // Only allow same-origin relative paths, never an open redirect.
  const target = next.startsWith("/") && !next.startsWith("//") ? next : "/";

  const form = new URLSearchParams({
    username: process.env.DEV_LOGIN_EMAIL ?? "admin@welyne.local",
    password: process.env.DEV_LOGIN_PASSWORD ?? "welyneAdmin2026",
  });

  let upstream: Response;
  try {
    upstream = await fetch(`${API_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { error: "Authentication service unreachable — is the api container up?" },
      { status: 502 }
    );
  }

  if (!upstream.ok) {
    return NextResponse.json(
      {
        error:
          "Dev auto-login rejected. Seed the admin user " +
          "(docker compose exec api python scripts/seed_admin.py) or set " +
          "DEV_LOGIN_EMAIL / DEV_LOGIN_PASSWORD.",
      },
      { status: 401 }
    );
  }

  const { access_token } = (await upstream.json()) as TokenResponse;

  const jar = await cookies();
  jar.set(SESSION_COOKIE, access_token, {
    httpOnly: true,
    secure: false,
    sameSite: "lax",
    path: "/",
    maxAge: EIGHT_HOURS,
  });

  return NextResponse.redirect(new URL(target, request.url));
}
