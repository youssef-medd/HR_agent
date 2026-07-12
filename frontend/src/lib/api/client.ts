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

export interface ApplicationCreated {
  application_id: number;
  state: string;
}

export interface CVExperience {
  title: string;
  company: string;
  start: string;
  end: string;
  summary: string;
}

export interface CVEducation {
  degree: string;
  institution: string;
  year: string;
}

export interface CVData {
  full_name: string;
  email: string;
  phone: string;
  location: string;
  summary: string;
  skills: string[];
  languages: string[];
  years_experience: number | null;
  experiences: CVExperience[];
  education: CVEducation[];
}

export interface ApplicationView {
  id: number;
  job_id: number;
  candidate_ref: string;
  state: string;
  cv: CVData | null;
}

export interface ApplicationSummary {
  id: number;
  job_id: number;
  candidate_ref: string;
  state: string;
  full_name: string | null;
  created_at: string;
}

export const API_URL = process.env.API_URL ?? "http://localhost:8000";

export const SESSION_COOKIE = "welyne_session";
