"use client";

/**
 * Candidate detail sheet — opened by clicking a row in the candidates table.
 *
 * The table row only carries the summary (name, job, score, stage), so the
 * sheet fetches `/api/applications/{id}` for the full view: where the
 * application stands in the pipeline and what is still ahead of it, the A4
 * score card, the A5 pre-screening recap, and the parsed CV.
 */

import * as React from "react";
import { Check, Loader2 } from "lucide-react";

import { StateBadge } from "@/components/shell/state-badge";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { ApplicationSummary, ApplicationView, ScoreCard } from "@/lib/api/client";
import { type ApplicationState } from "@/lib/mocks/types";

/** The happy path every application walks; branch states are handled apart. */
const PIPELINE: ApplicationState[] = [
  "RECEIVED",
  "PARSED",
  "SCORED",
  "SHORTLISTED",
  "PRESCREENING",
  "PRESCREENED",
  "INTERVIEW_SCHEDULED",
  "INTERVIEWED",
  "OFFER",
  "HIRED",
  "ONBOARDING",
];

const STEP_LABELS: Record<string, string> = {
  RECEIVED: "Received",
  PARSED: "CV parsed",
  SCORED: "Scored",
  SHORTLISTED: "Shortlisted",
  PRESCREENING: "Pre-screening",
  PRESCREENED: "Pre-screened",
  INTERVIEW_SCHEDULED: "Interview booked",
  INTERVIEWED: "Interviewed",
  OFFER: "Offer",
  HIRED: "Hired",
  ONBOARDING: "Onboarding",
};

/** States that stop the walk: nothing further is pending on the candidate. */
const STOPPED: Record<string, string> = {
  NEEDS_ATTENTION: "Paused — waiting on a recruiter.",
  DECLINED: "Closed — the candidate was declined.",
  POOL: "Kept in the talent pool for a future role.",
  DECLINE_PENDING: "Awaiting the recruiter's rejection decision.",
};

const SUBSCORES: { key: keyof ScoreCard; label: string }[] = [
  { key: "experience_match", label: "Experience" },
  { key: "skills_match", label: "Skills" },
  { key: "education_match", label: "Education" },
  { key: "sector_context_fit", label: "Sector & context" },
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-muted-foreground text-xs font-medium tracking-wide uppercase">
        {title}
      </h3>
      {children}
    </section>
  );
}

function Bar({ value }: { value: number }) {
  return (
    <span className="bg-muted relative h-1.5 w-full overflow-hidden rounded-full">
      <span
        className={`absolute inset-y-0 left-0 rounded-full ${value >= 70 ? "bg-primary" : "bg-muted-foreground/50"}`}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </span>
  );
}

/** Done / current / still to come, so "what is still in progress" is readable. */
function Progress({ state }: { state: string }) {
  const stopped = STOPPED[state];
  const currentIndex = PIPELINE.indexOf(state as ApplicationState);

  return (
    <div className="space-y-2">
      {stopped && <p className="text-muted-foreground text-sm">{stopped}</p>}
      <ol className="space-y-1.5">
        {PIPELINE.map((step, i) => {
          const done = currentIndex > -1 && i < currentIndex;
          const current = step === state;
          return (
            <li key={step} className="flex items-center gap-2 text-sm">
              <span
                className={`flex size-4 shrink-0 items-center justify-center rounded-full border text-[9px] ${
                  done
                    ? "border-primary bg-primary text-white"
                    : current
                      ? "border-primary text-primary"
                      : "border-muted-foreground/30 text-transparent"
                }`}
                aria-hidden
              >
                {done ? <Check className="size-2.5" /> : "•"}
              </span>
              <span
                className={
                  current
                    ? "text-foreground font-medium"
                    : done
                      ? "text-foreground"
                      : "text-muted-foreground"
                }
              >
                {STEP_LABELS[step]}
                {current && " — in progress"}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function CandidateSheet({
  row,
  onOpenChange,
}: {
  row: ApplicationSummary | null;
  onOpenChange: (open: boolean) => void;
}) {
  const [view, setView] = React.useState<ApplicationView | null>(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!row) return;
    let cancelled = false;
    setView(null);
    setLoading(true);
    fetch(`/api/applications/${row.id}`, { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: ApplicationView | null) => {
        if (!cancelled) setView(data);
      })
      .catch(() => {
        if (!cancelled) setView(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [row]);

  const cv = view?.cv ?? null;
  const score = view?.score ?? null;
  const prescreen = view?.prescreen ?? null;

  return (
    <Sheet open={row !== null} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-lg">
        {row && (
          <>
            <SheetHeader>
              <SheetTitle>{row.full_name || row.candidate_ref}</SheetTitle>
              <SheetDescription>
                {row.candidate_ref} · {row.job_title ?? `Job #${row.job_id}`} · applied{" "}
                {row.created_at.slice(0, 10)}
              </SheetDescription>
              <div className="pt-1">
                <StateBadge state={row.state as ApplicationState} />
              </div>
            </SheetHeader>

            <div className="space-y-6 px-4 pb-8">
              <Section title="Progress">
                <Progress state={row.state} />
              </Section>

              {loading && (
                <div className="flex justify-center py-6">
                  <Loader2 className="text-muted-foreground size-5 animate-spin" />
                </div>
              )}

              {!loading && !view && (
                <p className="text-muted-foreground text-sm">
                  Could not load this application&apos;s detail.
                </p>
              )}

              {score && (
                <Section title="Score (A4, masked judge)">
                  <div className="flex items-baseline gap-2">
                    <span className="text-2xl font-semibold">{score.overall}</span>
                    <span className="text-muted-foreground text-sm capitalize">
                      {score.recommendation}
                    </span>
                  </div>
                  <ul className="space-y-1.5">
                    {SUBSCORES.map(({ key, label }) => (
                      <li key={key} className="flex items-center gap-2 text-sm">
                        <span className="text-muted-foreground w-32 shrink-0">{label}</span>
                        <Bar value={Number(score[key] ?? 0)} />
                        <span className="w-8 shrink-0 text-right text-xs">
                          {String(score[key] ?? "")}
                        </span>
                      </li>
                    ))}
                  </ul>
                  {score.rationale && (
                    <p className="text-muted-foreground border-l-2 pl-3 text-sm">
                      {score.rationale}
                    </p>
                  )}
                </Section>
              )}

              {prescreen && (
                <Section title="Pre-screening (A5)">
                  {prescreen.summary && (
                    <p className="text-muted-foreground border-l-2 pl-3 text-sm whitespace-pre-line">
                      {prescreen.summary}
                    </p>
                  )}
                  {prescreen.answers && prescreen.answers.length > 0 && (
                    <ul className="space-y-2">
                      {prescreen.answers.map((a, i) => (
                        <li key={i} className="text-sm">
                          <p className="text-muted-foreground">{a.q}</p>
                          <p>{a.a || "—"}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                  {!prescreen.summary && !prescreen.answers?.length && (
                    <p className="text-muted-foreground text-sm">
                      Started ({prescreen.status ?? "in progress"}) — no answers recorded yet.
                    </p>
                  )}
                </Section>
              )}

              {cv && (
                <Section title="CV">
                  {cv.years_experience !== null && (
                    <p className="text-sm">{cv.years_experience} years of experience</p>
                  )}
                  {cv.skills.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {cv.skills.map((s) => (
                        <span key={s} className="chip bg-muted text-muted-foreground">
                          {s}
                        </span>
                      ))}
                    </div>
                  )}
                  {cv.experiences.length > 0 && (
                    <ul className="space-y-2">
                      {cv.experiences.map((e, i) => (
                        <li key={i} className="text-sm">
                          <p className="font-medium">
                            {e.title}
                            {e.company && ` · ${e.company}`}
                          </p>
                          <p className="text-muted-foreground text-xs">
                            {[e.start, e.end].filter(Boolean).join(" – ")}
                          </p>
                        </li>
                      ))}
                    </ul>
                  )}
                </Section>
              )}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
