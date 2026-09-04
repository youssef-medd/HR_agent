"use client";

import * as React from "react";
import {
  AlertTriangle,
  CalendarCheck,
  CheckCircle2,
  ExternalLink,
  Loader2,
} from "lucide-react";

import type { BookingSlot, BookingView } from "@/lib/api/client";

const PANEL =
  "rounded-3xl border border-white/[0.08] bg-black/55 shadow-[0_8px_40px_rgba(0,0,0,0.5)] backdrop-blur-xl";

const SLOT =
  "w-full rounded-xl border px-4 py-2.5 text-left text-sm transition-colors disabled:opacity-60";

export function BookingPanel({ email, appId }: { email: string; appId: number }) {
  const [view, setView] = React.useState<BookingView | null>(null);
  const [picked, setPicked] = React.useState<string>("");
  const [slot, setSlot] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [replanning, setReplanning] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    const res = await fetch(
      `/api/public/booking?email=${encodeURIComponent(email)}&application_id=${appId}`,
      { cache: "no-store" },
    );
    if (res.ok) setView((await res.json()) as BookingView);
  }, [email, appId]);

  React.useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);

  async function post(path: string, body: Record<string, unknown>) {
    setError(null);
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, application_id: appId, ...body }),
    });
    if (!res.ok) {
      const data = (await res.json().catch(() => ({}))) as { detail?: string };
      setError(data.detail ?? "Something went wrong. Please try again.");
      return false;
    }
    return true;
  }

  async function confirm() {
    setSaving(true);
    const ok = await post("/api/public/booking/confirm", {
      slot_at: picked || null,
      slot: slot.trim() || null,
    });
    setSaving(false);
    if (ok) {
      setSlot("");
      setPicked("");
      setTimeout(load, 800);
    }
  }

  async function reschedule(at: string) {
    setSaving(true);
    const ok = await post("/api/public/booking/reschedule", { slot_at: at });
    setSaving(false);
    if (ok) {
      setReplanning(false);
      setTimeout(load, 500);
    }
  }

  if (!view) return null;

  const slots: BookingSlot[] = view.slots ?? [];

  // Pre-screening is done but the recruiter has not yet approved the invitation,
  // so no times exist to offer. Say that, rather than showing an empty form the
  // candidate cannot complete.
  if (!view.booked && slots.length === 0 && !view.scheduled_at) {
    return (
      <div className={`${PANEL} flex flex-col items-center gap-2 p-6 text-center`}>
        <CalendarCheck className="text-primary size-7" />
        <p className="font-medium text-white">Thanks — that&apos;s everything we need</p>
        <p className="text-sm text-white/45">
          Your answers are with the recruiting team. If they move you forward, interview
          times will appear here and we&apos;ll message you.
        </p>
      </div>
    );
  }

  function slotList(onPick: (at: string) => void, active?: string) {
    return (
      <div className="grid gap-2">
        {slots.map((s) => (
          <button
            key={s.at}
            type="button"
            disabled={saving}
            onClick={() => onPick(s.at)}
            className={`${SLOT} ${
              active === s.at
                ? "border-primary/70 bg-primary/15 text-white"
                : "border-white/10 bg-white/[0.03] text-white/80 hover:border-white/25 hover:bg-white/[0.07]"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>
    );
  }

  // --- Booked -------------------------------------------------------------
  if (view.booked) {
    return (
      <div className={`${PANEL} p-6`}>
        <div className="flex flex-col items-center gap-2 text-center">
          <CheckCircle2 className="size-8 text-emerald-400" />
          <p className="font-medium text-white">Interview scheduled</p>
          {view.when && <p className="text-sm text-white/50">{view.when}</p>}
          {view.no_show && (
            <p className="flex items-center gap-1.5 text-xs text-amber-400">
              <AlertTriangle className="size-3.5" />
              We missed you — pick a new time below.
            </p>
          )}
        </div>

        {view.can_reschedule && (
          <div className="mt-5 border-t border-white/[0.08] pt-4">
            {!replanning ? (
              <button
                type="button"
                onClick={() => setReplanning(true)}
                className="w-full rounded-xl border border-white/12 bg-white/[0.04] py-2.5 text-sm text-white transition-colors hover:border-white/25 hover:bg-white/[0.07]"
              >
                Need another time? Reschedule
              </button>
            ) : (
              <>
                <p className="mb-3 text-xs text-white/50">
                  Pick a new time — your calendar invite is updated automatically.
                </p>
                {slots.length > 0 ? (
                  slotList((at) => reschedule(at))
                ) : (
                  <p className="text-xs text-white/40">
                    No open times left. Reply to your invitation email and we&apos;ll find one.
                  </p>
                )}
                {view.link && (
                  <a
                    href={view.link}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl border border-white/12 bg-white/[0.04] py-2.5 text-sm text-white transition-colors hover:border-white/25 hover:bg-white/[0.07]"
                  >
                    Choose another time <ExternalLink className="size-4" />
                  </a>
                )}
                <button
                  type="button"
                  onClick={() => setReplanning(false)}
                  className="mt-2 w-full py-2 text-xs text-white/40 transition-colors hover:text-white/70"
                >
                  Keep my current time
                </button>
              </>
            )}
            {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
          </div>
        )}
      </div>
    );
  }

  // --- Awaiting a booking -------------------------------------------------
  return (
    <div className={`${PANEL} p-6`}>
      <div className="mb-3 flex items-center gap-2">
        <CalendarCheck className="text-primary size-5" />
        <p className="font-heading text-sm font-semibold text-white">Book your interview</p>
      </div>
      <p className="mb-4 text-sm text-white/45">
        {slots.length > 0
          ? "Choose one of these times — we'll send the calendar invite straight away."
          : "Tell us when suits you and we'll confirm."}
      </p>

      {slots.length > 0 && (
        <div className="mb-4">{slotList((at) => setPicked(at), picked)}</div>
      )}

      {view.link && (
        <a
          href={view.link}
          target="_blank"
          rel="noreferrer"
          className="mb-4 flex w-full items-center justify-center gap-2 rounded-xl border border-white/12 bg-white/[0.04] py-2.5 text-sm text-white transition-colors hover:border-white/25 hover:bg-white/[0.07]"
        >
          See more times <ExternalLink className="size-4" />
        </a>
      )}

      <button
        type="button"
        onClick={confirm}
        disabled={saving || (!picked && !slot.trim())}
        className="from-primary flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r to-[#ff8a33] py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-40"
      >
        {saving ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <CalendarCheck className="size-4" />
        )}
        {saving ? "Confirming…" : "Confirm this time"}
      </button>

      <details className="mt-3">
        <summary className="cursor-pointer list-none text-xs text-white/35 underline underline-offset-4 transition-colors hover:text-white/70">
          None of these work?
        </summary>
        <div className="mt-2.5 grid gap-2">
          <label htmlFor="slot" className="text-xs text-white/60">
            Tell us when you are free and we&apos;ll come back to you
          </label>
          <input
            id="slot"
            value={slot}
            onChange={(e) => setSlot(e.target.value)}
            placeholder="e.g. Tuesday afternoon"
            className="focus:border-primary/50 w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white transition-colors placeholder:text-white/25 focus:outline-none"
          />
        </div>
      </details>

      {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
    </div>
  );
}
