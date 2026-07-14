import type { ApplicationState } from "@/lib/mocks/types";

/** Rounded soft-background chips per pipeline state (light SaaS language). */
const STATE_STYLES: Record<string, string> = {
  RECEIVED: "bg-muted text-muted-foreground",
  PARSED: "bg-blue-50 text-blue-600 dark:bg-blue-500/15 dark:text-blue-400",
  SCORED: "bg-violet-50 text-violet-600 dark:bg-violet-500/15 dark:text-violet-400",
  SHORTLISTED: "bg-orange-50 text-primary dark:bg-orange-500/15",
  POOL: "bg-slate-100 text-slate-600 dark:bg-slate-500/15 dark:text-slate-400",
  DECLINE_PENDING: "bg-red-50 text-red-600 dark:bg-red-500/15 dark:text-red-400",
  PRESCREENING: "bg-cyan-50 text-cyan-700 dark:bg-cyan-500/15 dark:text-cyan-400",
  PRESCREENED: "bg-cyan-50 text-cyan-700 dark:bg-cyan-500/15 dark:text-cyan-400",
  INTERVIEW_SCHEDULED: "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400",
  INTERVIEWED: "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400",
  OFFER: "bg-orange-50 text-primary dark:bg-orange-500/15",
  HIRED: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  ONBOARDING: "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400",
  DECLINED: "bg-muted text-muted-foreground",
  NEEDS_ATTENTION: "bg-red-50 text-red-600 dark:bg-red-500/15 dark:text-red-400",
};

function titleCase(s: string): string {
  const words = s.replaceAll("_", " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function StateBadge({ state }: { state: ApplicationState }) {
  return (
    <span className={`chip ${STATE_STYLES[state] ?? "bg-muted text-muted-foreground"}`}>
      <span className="size-1.5 shrink-0 rounded-full bg-current" aria-hidden />
      {titleCase(state)}
    </span>
  );
}
