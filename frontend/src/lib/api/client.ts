/**
 * Typed mirrors of the FastAPI response models (api/app/routers/*).
 * Server-only code should use `API_URL` (no NEXT_PUBLIC prefix); anything
 * running in the browser goes through the /api/* BFF route handlers instead.
 */

export type Role = "admin" | "recruiter" | "viewer";

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface MeResponse {
  id: number;
  email: string;
  role: Role;
}

export interface HelloRequest {
  prompt: string;
}

export interface HelloResponse {
  reply: string;
}

export const API_URL = process.env.API_URL ?? "http://localhost:8000";

export const SESSION_COOKIE = "welyne_session";
