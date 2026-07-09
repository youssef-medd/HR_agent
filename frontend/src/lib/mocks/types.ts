/**
 * MOCK-ONLY types. These mirror the backend's SQLAlchemy models
 * (api/app/models/*) and the orchestrator state machine
 * (worker/orchestrator/state_machine.py) so screens match the future
 * API shapes. Delete this folder as real endpoints land.
 */

export const APPLICATION_STATES = [
  "RECEIVED",
  "PARSED",
  "SCORED",
  "SHORTLISTED",
  "POOL",
  "DECLINE_PENDING",
  "PRESCREENING",
  "PRESCREENED",
  "INTERVIEW_SCHEDULED",
  "INTERVIEWED",
  "OFFER",
  "HIRED",
  "ONBOARDING",
  "DECLINED",
  "NEEDS_ATTENTION",
] as const;

export type ApplicationState = (typeof APPLICATION_STATES)[number];

export interface MockCandidate {
  ref: string; // candidate_ref on applications
  fullName: string;
  email: string;
  jobTitle: string;
  jobId: number;
  score: number | null; // 0-100, null before SCORED
  state: ApplicationState;
  appliedAt: string; // ISO
  location: string;
  source: "LinkedIn" | "Direct" | "Referral" | "Tanitjobs" | "Email";
}

export interface MockJob {
  id: number;
  title: string;
  department: string;
  location: string;
  status: "draft" | "published" | "closed";
  applicants: number;
  shortlisted: number;
  publishedAt: string | null;
}

export interface MockApplication {
  id: number;
  jobId: number;
  jobTitle: string;
  candidateRef: string;
  candidateName: string;
  state: ApplicationState;
  updatedAt: string;
}

export interface MockAttentionItem {
  id: number;
  applicationId: number;
  candidateName: string;
  jobTitle: string;
  reason: string; // e.g. "human_gate", "illegal_transition", "retries_exhausted"
  gate: "rejection" | "offer" | null;
  status: "open" | "resolved";
  createdAt: string;
  context: string; // human-readable summary of context JSONB
}
