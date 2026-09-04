"use client";

import * as React from "react";
import { CheckCircle2, FileUp, Loader2 } from "lucide-react";

import type { OnboardingView } from "@/lib/api/client";

// Images allowed: a phone photo of an ID or a RIB is the normal case.
const DOC_ACCEPT = ".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp";

export function OnboardingPanel({ email, appId }: { email: string; appId: number }) {
  const [view, setView] = React.useState<OnboardingView | null>(null);
  const [busy, setBusy] = React.useState<number | null>(null);

  const load = React.useCallback(async () => {
    const res = await fetch(
      `/api/public/onboarding?email=${encodeURIComponent(email)}&application_id=${appId}`,
      { cache: "no-store" },
    );
    if (res.ok) setView((await res.json()) as OnboardingView);
  }, [email, appId]);

  React.useEffect(() => {
    load();
  }, [load]);

  async function upload(taskId: number, file: File) {
    setBusy(taskId);
    const form = new FormData();
    form.set("email", email);
    form.set("application_id", String(appId));
    form.set("task_id", String(taskId));
    form.set("file", file);
    const res = await fetch("/api/public/onboarding/upload", { method: "POST", body: form });
    setBusy(null);
    if (res.ok) setView((await res.json()) as OnboardingView);
  }

  if (!view) return null;

  const documents = view.tasks.filter((t) => t.category === "document");
  const other = view.tasks.filter((t) => t.category !== "document");
  const pct =
    view.documents_total > 0
      ? Math.round((view.documents_received / view.documents_total) * 100)
      : 0;

  return (
    <div className="rounded-3xl border border-white/[0.08] bg-black/55 p-6 shadow-[0_8px_40px_rgba(0,0,0,0.5)] backdrop-blur-xl">
      <div className="mb-4">
        <p className="font-heading text-sm font-semibold text-white">
          Welcome — let&apos;s get you set up
        </p>
        <p className="text-sm text-white/45">
          Upload the documents below. Your recruiter is notified as you go.
        </p>
      </div>

      {documents.length > 0 && (
        <>
          <div className="mb-4">
            <div className="mb-1 flex justify-between text-xs">
              <span className="text-white/45">Documents collected</span>
              <span className="tabular-nums text-white/70">
                {view.documents_received}/{view.documents_total}
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-white/10">
              <div className="bg-primary h-full rounded-full" style={{ width: `${pct}%` }} />
            </div>
          </div>

          <ul className="mb-4 space-y-2">
            {documents.map((t) => (
              <li
                key={t.id}
                className="flex items-center justify-between gap-3 rounded-xl border border-white/[0.08] bg-white/[0.03] p-3"
              >
                <span className="flex items-center gap-2 text-sm text-white/85">
                  {t.uploaded ? (
                    <CheckCircle2 className="size-4 text-emerald-400" />
                  ) : (
                    <FileUp className="size-4 text-white/30" />
                  )}
                  {t.label}
                </span>
                {t.uploaded ? (
                  <span className="text-xs text-emerald-400">Received</span>
                ) : (
                  <label className="cursor-pointer">
                    <span className="hover:border-primary/50 inline-flex items-center gap-1.5 rounded-lg border border-white/12 bg-white/[0.04] px-3 py-1.5 text-xs text-white transition-colors">
                      {busy === t.id ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : (
                        <FileUp className="size-3.5" />
                      )}
                      Upload
                    </span>
                    <input
                      type="file"
                      accept={DOC_ACCEPT}
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) upload(t.id, f);
                      }}
                    />
                  </label>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {view.complete && (
        <p className="mb-4 rounded-xl border border-emerald-400/25 bg-emerald-500/10 p-3 text-sm text-emerald-400">
          All documents received — you&apos;re all set. Welcome aboard!
        </p>
      )}

      {other.length > 0 && (
        <div>
          <p className="mb-2 text-xs tracking-wide text-white/40 uppercase">Your first week</p>
          <ul className="space-y-1 text-sm text-white/55">
            {other.map((t) => (
              <li key={t.id}>• {t.label}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
