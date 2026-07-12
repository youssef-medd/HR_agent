import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { API_URL, SESSION_COOKIE, type MeResponse } from "./client";

/**
 * Reads the session cookie and validates it against GET /auth/me.
 * Returns null when there is no cookie or the token is rejected —
 * the middleware only checks cookie presence, this is the real gate.
 */
export async function getServerSession(): Promise<MeResponse | null> {
  const jar = await cookies();
  const token = jar.get(SESSION_COOKIE)?.value;
  if (!token) return null;

  try {
    const res = await fetch(`${API_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as MeResponse;
  } catch {
    return null;
  }
}

export async function requireUser(): Promise<MeResponse> {
  const user = await getServerSession();
  if (!user) redirect("/login");
  return user;
}

export async function getSessionToken(): Promise<string | null> {
  const jar = await cookies();
  return jar.get(SESSION_COOKIE)?.value ?? null;
}

/** Authenticated server-side GET against the FastAPI backend. Returns `fallback` on any failure. */
export async function apiGet<T>(path: string, fallback: T): Promise<T> {
  const token = await getSessionToken();
  if (!token) return fallback;
  try {
    const res = await fetch(`${API_URL}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return fallback;
    return (await res.json()) as T;
  } catch {
    return fallback;
  }
}
