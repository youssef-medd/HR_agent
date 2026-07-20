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
  score: number | null;
  recommendation: string | null;
  created_at: string;
}

export interface JobView {
  id: number;
  title: string;
  department: string | null;
  location: string | null;
  description: string;
  status: string;
  created_at: string;
  applicants: number;
  shortlisted: number;
}

export interface AttentionItem {
  id: number;
  application_id: number;
  candidate_ref: string | null;
  full_name: string | null;
  reason: string;
  gate: string | null;
  context: Record<string, unknown>;
  status: string;
  created_at: string;
}

export interface SourcingKit {
  boolean_search: string;
  keywords: string[];
  platforms: string[];
  outreach_subject: string;
  outreach_message: string;
}

export interface FunnelStage {
  stage: string;
  reached: number;
  rate_from_prev: number;
  avg_hours_from_received: number | null;
}

export interface JobFunnel {
  job_id: number;
  title: string;
  applicants: number;
  shortlisted: number;
}

export interface ReportOverview {
  total_applications: number;
  by_state: Record<string, number>;
  funnel: FunnelStage[];
  avg_score: number | null;
  shortlist_rate: number;
  hire_rate: number;
  open_gates: number;
  per_job: JobFunnel[];
}

export const API_URL = process.env.API_URL ?? "http://localhost:8000";

export const SESSION_COOKIE = "welyne_session";
