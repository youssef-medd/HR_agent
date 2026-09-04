"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Check,
  Hash,
  Loader2,
  Mail,
  MailCheck,
  Search,
  Send,
} from "lucide-react";

import { GlassCard, PublicShell } from "@/components/apply/public-shell";
import { BookingPanel } from "@/components/portal/booking-panel";
import { OnboardingPanel } from "@/components/portal/onboarding-panel";
import { PrescreenChat } from "@/components/portal/prescreen-chat";
import { cn } from "@/lib/utils";
import type { TrackedApplication } from "@/lib/api/client";

/**
 * Candidate-facing stages. The pipeline has 15 internal states; a candidate
 * should see the five that mean something to them, so each stage owns the set
 * of machine states that map onto it.
 */
const STAGES: { label: string; states: string[] }[] = [
  { label: "Application received", states: ["RECEIVED"] },
  { label: "CV reviewed", states: ["PARSED", "SCORED", "SHORTLISTED", "POOL"] },
  { label: "Pre-screening", states: ["PRESCREENING"] },
  {
    // PRESCREENED belongs here: the questions are answered and the candidate is
    // now choosing an interview time.
    label: "Interview",
    states: ["PRESCREENED", "INTERVIEW_SCHEDULED", "INTERVIEWED", "OFFER"],
  },
  {
    label: "Final decision",
    states: ["HIRED", "ONBOARDING", "DECLINED", "DECLINE_PENDING"],
  },
];

/** What the candidate should expect (or do) while sitting in a given state. */
const STATE_HINT: Record<string, string> = {
  RECEIVED: "We have your application",
  PARSED: "Being reviewed",
  SCORED: "Being reviewed",
  SHORTLISTED: "Shortlisted",
  PRESCREENING: "Answer the questions below",
  PRESCREENED: "Choose a time below",
  INTERVIEW_SCHEDULED: "Interview booked",
  INTERVIEWED: "Awaiting the team's decision",
  OFFER: "Offer on its way",
  HIRED: "Welcome aboard",
  ONBOARDING: "Complete your onboarding below",
  DECLINE_PENDING: "Under final review",
  DECLINED: "Not moving forward",
  POOL: "Kept for future roles",
};

/** Index of the stage the application is currently sitting in. */
function stageIndex(state: string): number {
  const found = STAGES.findIndex((s) => s.states.includes(state));
  // NEEDS_ATTENTION is an internal hold, not a candidate-visible step — keep
  // the last known position rather than dropping off the stepper.
  return found === -1 ? 0 : found;
}

const inputClass =
  "w-full rounded-xl border border-white/10 bg-white/[0.03] py-2.5 pr-4 pl-10 text-sm " +
  "text-white placeholder:text-white/25 transition-colors duration-200 " +
  "focus:border-primary/50 focus:bg-white/[0.05] focus:outline-none";

export default function PortalPage() {
  const [email, setEmail] = React.useState("");
  const [ref, setRef] = React.useState("");
  const [token, setToken] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [linkSent, setLinkSent] = React.useState(false);
  const [showFallback, setShowFallback] = React.useState(false);
  const [result, setResult] = React.useState<TrackedApplication | null>(null);
  const [erased, setErased] = React.useState(false);

  /** Load an application by signed token, or by the legacy email + reference. */
  const lookup = React.useCallback(
    async (params: { token?: string; email?: string; ref?: string }) => {
      const query = params.token
        ? `t=${encodeURIComponent(params.token)}`
        : `email=${encodeURIComponent((params.email ?? "").trim())}` +
          `&application_id=${encodeURIComponent((params.ref ?? "").trim())}`;

      setError(null);
      setResult(null);
      setLoading(true);
      const res = await fetch(`/api/public/track?${query}`, { cache: "no-store" });
      setLoading(false);

      if (!res.ok) {
        setError(
          params.token
            ? "That link is invalid or has expired. Request a new one below."
            : "No application found for that email and reference.",
        );
        return;
      }
      const data = (await res.json()) as TrackedApplication;
      // A token arrival never typed an address; the child panels identify by
      // email, so adopt the verified one the API echoes back.
      if (data.email) setEmail(data.email);
      setResult(data);
    },
    [],
  );

  // Auto-load from an emailed link. `?t=` is the signed token; `?email=&ref=`
  // is the older form, still honoured so links already in inboxes keep working.
  React.useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const t = p.get("t");
    if (t) {
      setToken(t);
      lookup({ token: t });
      return;
    }
    const e = p.get("email") ?? "";
    const r = p.get("ref") ?? "";
    if (e && r) {
      setEmail(e);
      setRef(r);
      lookup({ email: e, ref: r });
    }
  }, [lookup]);

  /**
   * Email the candidate their link instead of asking for a reference number.
   * The response is deliberately identical whether or not the address has
   * applied, so the UI must not branch on it either.
   */
  async function requestLink(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (loading || !email.trim()) return;
    setError(null);
    setLoading(true);
    await fetch("/api/public/portal/request-link", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: email.trim() }),
    }).catch(() => null);
    setLoading(false);
    setLinkSent(true);
  }

  function onFallbackSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (loading) return;
    lookup({ email, ref });
  }

  async function eraseData() {
    if (!result) return;
    if (
      !window.confirm("Permanently erase all your personal data? This cannot be undone.")
    )
      return;
    const res = await fetch("/api/public/candidates/erase", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(
        token
          ? { token }
          : { email: email.trim(), application_id: result.id },
      ),
    });
    if (res.ok) {
      setErased(true);
      setResult(null);
    }
  }

  const current = result ? stageIndex(result.state) : 0;

  return (
    <PublicShell>
      <div className="mx-auto max-w-2xl">
        <Link
          href="/apply"
          className="mb-7 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-white/60 transition-colors duration-200 hover:border-white/25 hover:text-white"
        >
          <ArrowLeft className="size-3.5" /> Open roles
        </Link>

        <header className="mb-8">
          <p className="text-primary text-sm font-medium tracking-wide">
            Welyne · Candidate portal
          </p>
          <h1 className="font-heading mt-2 text-4xl font-semibold tracking-tight text-white">
            Track your application
          </h1>
          <p className="mt-3 text-sm text-white/45">
            Enter the email you applied with — we&apos;ll send you a link.
          </p>
        </header>

        {/* Hidden once a token has already loaded an application. */}
        {!token && (
          <GlassCard className="mb-6 p-6">
            {linkSent ? (
              <div className="py-6 text-center">
                <span className="bg-primary/15 mx-auto mb-4 flex size-12 items-center justify-center rounded-2xl">
                  <MailCheck className="text-primary size-6" aria-hidden />
                </span>
                <p className="font-heading text-lg font-semibold text-white">
                  Check your inbox
                </p>
                <p className="mx-auto mt-2 max-w-sm text-sm text-white/50">
                  If <span className="text-white/80">{email.trim()}</span> has an
                  application with us, a link is on its way. It expires in 7 days.
                </p>
                <button
                  type="button"
                  onClick={() => setLinkSent(false)}
                  className="text-primary mt-4 text-sm hover:underline"
                >
                  Use a different email
                </button>
              </div>
            ) : (
              <form onSubmit={requestLink} className="grid gap-4">
                <div>
                  <label
                    htmlFor="email"
                    className="mb-2 block text-sm font-medium text-white/80"
                  >
                    Email
                  </label>
                  <div className="relative">
                    <Mail
                      className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-white/30"
                      aria-hidden
                    />
                    <input
                      id="email"
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="jane@example.com"
                      className={inputClass}
                    />
                  </div>
                </div>
                <button
                  type="submit"
                  disabled={loading}
                  className="from-primary mt-1 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r to-[#ff8a33] py-3 text-sm font-semibold text-white shadow-[0_8px_30px_rgba(255,107,0,0.25)] transition-all duration-200 hover:shadow-[0_8px_36px_rgba(255,107,0,0.4)] disabled:opacity-60"
                >
                  {loading ? (
                    <>
                      <Loader2 className="size-4 animate-spin" /> Sending…
                    </>
                  ) : (
                    <>
                      <Send className="size-4" /> Email me my link
                    </>
                  )}
                </button>
                {error && <p className="text-sm text-red-400">{error}</p>}

                {/* Fallback for a candidate whose link expired or never arrived. */}
                {showFallback ? (
                  <div className="mt-2 border-t border-white/[0.08] pt-4">
                    <label
                      htmlFor="ref"
                      className="mb-2 block text-sm font-medium text-white/80"
                    >
                      Application reference
                    </label>
                    <div className="relative">
                      <Hash
                        className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-white/30"
                        aria-hidden
                      />
                      <input
                        id="ref"
                        inputMode="numeric"
                        value={ref}
                        onChange={(e) => setRef(e.target.value)}
                        placeholder="e.g. 12"
                        className={inputClass}
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        onFallbackSubmit({
                          preventDefault: () => {},
                        } as React.FormEvent<HTMLFormElement>)
                      }
                      disabled={loading || !email.trim() || !ref.trim()}
                      className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-white/12 bg-white/[0.04] py-2.5 text-sm text-white transition-colors hover:border-white/25 disabled:opacity-50"
                    >
                      <Search className="size-4" /> Track with reference
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setShowFallback(true)}
                    className="text-xs text-white/35 underline underline-offset-4 transition-colors hover:text-white/70"
                  >
                    I have my reference number
                  </button>
                )}
              </form>
            )}
          </GlassCard>
        )}

        {result && (
          <GlassCard className="p-7">
            <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-heading text-xl font-semibold text-white">
                  {result.job_title ?? "Your application"}
                </h2>
                <p className="mt-1 text-sm text-white/40">Reference #{result.id}</p>
              </div>
              <span className="border-primary/40 bg-primary/10 text-primary rounded-full border px-3 py-1.5 text-xs font-medium">
                {result.state.replaceAll("_", " ").toLowerCase()}
              </span>
            </div>

            <ol>
              {STAGES.map((stage, i) => {
                const done = i < current;
                const active = i === current;
                return (
                  <li key={stage.label} className="flex gap-3.5">
                    {/* marker + connector */}
                    <div className="flex flex-col items-center">
                      <span
                        className={cn(
                          "flex size-5 shrink-0 items-center justify-center rounded-full border transition-colors",
                          done && "border-emerald-400/50 bg-emerald-400/15",
                          active && "border-primary bg-primary/20",
                          !done && !active && "border-white/15 bg-transparent",
                        )}
                      >
                        {done ? (
                          <Check className="size-3 text-emerald-400" aria-hidden />
                        ) : active ? (
                          <span className="bg-primary size-2 rounded-full" />
                        ) : null}
                      </span>
                      {i < STAGES.length - 1 && (
                        <span
                          className={cn(
                            "my-1 w-px flex-1",
                            done ? "bg-emerald-400/30" : "bg-white/10",
                          )}
                        />
                      )}
                    </div>

                    <div className={cn("pb-6", i === STAGES.length - 1 && "pb-0")}>
                      <p
                        className={cn(
                          "text-sm",
                          active
                            ? "font-semibold text-white"
                            : done
                              ? "text-white/70"
                              : "text-white/30",
                        )}
                      >
                        {stage.label}
                      </p>
                      {active && (
                        <p className="text-primary mt-0.5 text-xs">
                          {STATE_HINT[result.state] ?? "In progress"}
                        </p>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>

            <p className="mt-2 border-t border-white/[0.08] pt-4 text-xs text-white/35">
              Applied {result.created_at.slice(0, 10)}
              {result.timeline.length > 0 &&
                ` · last update ${new Date(
                  result.timeline[result.timeline.length - 1].at,
                ).toLocaleString()}`}
            </p>
          </GlassCard>
        )}

        {result && result.state === "PRESCREENING" && (
          <div className="mt-6">
            <PrescreenChat email={email.trim()} appId={result.id} />
          </div>
        )}

        {result &&
          (result.state === "PRESCREENED" || result.state === "INTERVIEW_SCHEDULED") && (
            <div className="mt-6">
              <BookingPanel email={email.trim()} appId={result.id} />
            </div>
          )}

        {result && (result.state === "HIRED" || result.state === "ONBOARDING") && (
          <div className="mt-6">
            <OnboardingPanel email={email.trim()} appId={result.id} />
          </div>
        )}

        {result && (
          <div className="mt-6 text-center">
            <button
              type="button"
              onClick={eraseData}
              className="text-xs text-white/30 underline underline-offset-4 transition-colors hover:text-red-400"
            >
              Erase my personal data (RGPD)
            </button>
          </div>
        )}

        {erased && (
          <p className="mt-6 text-center text-sm text-emerald-400">
            Your personal data has been erased.
          </p>
        )}
      </div>
    </PublicShell>
  );
}
