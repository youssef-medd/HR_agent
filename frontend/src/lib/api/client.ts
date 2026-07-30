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

export interface ScoreEvidence {
  dimension: string;
  quote: string;
}

export interface ScoreCard {
  overall: number;
  skills_match: number;
  experience_match: number;
  education_match: number;
  sector_context_fit: number;
  rationale: string;
  recommendation: string;
  evidence: ScoreEvidence[];
  hard_filter_failures?: string[];
  weights_used?: Record<string, number> | string;
  provenance?: { model: string; prompt_version: string; run_seed: number };
  semantic?: { skills_sim: number; experience_sim: number; prerank_score: number };
}

export interface PrescreenMessage {
  role: string;
  text: string;
}

export interface PrescreenBlock {
  status?: string;
  channel?: string;
  consent?: { given: boolean | null; at: string | null };
  answers?: { q: string; a: string; at?: string }[];
  transcript?: PrescreenMessage[];
  summary?: string;
  slots?: Record<string, string>;
  flags?: {
    contradictions?: string[];
    red_flags?: string[];
    great_signals?: string[];
    conversation?: string[];
  };
}

export interface ApplicationView {
  id: number;
  job_id: number;
  candidate_ref: string;
  state: string;
  cv: CVData | null;
  score: ScoreCard | null;
  prescreen: PrescreenBlock | null;
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
  spec?: JobIntake | null;
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

export interface JobSpecStruct {
  seniority: string;
  location: string;
  salary_range: string;
  missions: string[];
  must_have: string[];
  nice_to_have: string[];
  languages: string[];
  eliminatory_criteria: string[];
}

export interface JobWeights {
  skills: number;
  experience: number;
  education: number;
}

export interface JobChannels {
  linkedin_post: string;
  job_board_text: string;
  careers_page: string;
  whatsapp_blurb: string;
}

export interface JobIntake {
  spec: JobSpecStruct;
  weights: JobWeights;
  channels: JobChannels;
}

export interface TimelineEntry {
  state: string;
  at: string;
}

export interface PrescreenMessage {
  role: string;
  text: string;
}

export interface PrescreenView {
  state: string;
  status: string;
  channel: string;
  transcript: PrescreenMessage[];
  awaiting: boolean;
  done: boolean;
}

export interface BookingView {
  state: string;
  link: string;
  awaiting: boolean;
  booked: boolean;
  when: string | null;
}

export interface TrackedApplication {
  id: number;
  state: string;
  job_title: string | null;
  created_at: string;
  timeline: TimelineEntry[];
}

export interface OnboardingTask {
  when: string;
  task: string;
}

export interface OnboardingKit {
  welcome_message: string;
  checklist: string[];
  week_one_plan: OnboardingTask[];
  documents: string[];
}

export interface OutreachDraft {
  tone: string;
  subject: string;
  message: string;
}

export interface SourcingKit {
  search_strings: string[];
  keywords: string[];
  platforms: string[];
  outreach: OutreachDraft[];
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
  avg_score?: number | null;
  score_buckets?: Record<string, number>;
}

export interface SourceConversion {
  applied: number;
  shortlisted: number;
  hired: number;
  shortlist_rate: number;
  hire_rate: number;
}

export interface ReportOverview {
  total_applications: number;
  by_state: Record<string, number>;
  by_source: Record<string, number>;
  source_conversion: Record<string, SourceConversion>;
  funnel: FunnelStage[];
  avg_score: number | null;
  score_distribution: Record<string, number>;
  shortlist_rate: number;
  hire_rate: number;
  open_gates: number;
  per_job: JobFunnel[];
}

export const API_URL = process.env.API_URL ?? "http://localhost:8000";

export const SESSION_COOKIE = "welyne_session";
