import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { API_URL, SESSION_COOKIE, type TokenResponse } from "@/lib/api/client";

const EIGHT_HOURS = 8 * 60 * 60;

export async function POST(request: Request) {
  let body: { email?: string; password?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }

  if (!body.email || !body.password) {
    return NextResponse.json(
      { error: "Email and password are required" },
      { status: 400 }
    );
  }

  // FastAPI expects OAuth2 form encoding: username=<email>&password=<pw>
  const form = new URLSearchParams({
    username: body.email,
    password: body.password,
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
      { error: "Authentication service unreachable" },
      { status: 502 }
    );
  }

  if (!upstream.ok) {
    return NextResponse.json(
      { error: "Invalid email or password" },
      { status: 401 }
    );
  }

  const { access_token } = (await upstream.json()) as TokenResponse;

  const jar = await cookies();
  jar.set(SESSION_COOKIE, access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: EIGHT_HOURS,
  });

  return NextResponse.json({ ok: true });
}
