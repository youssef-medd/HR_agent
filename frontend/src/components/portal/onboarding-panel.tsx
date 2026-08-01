"use client";

import * as React from "react";
import { CheckCircle2, FileUp, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { OnboardingView } from "@/lib/api/client";

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
    <div className="surface p-6">
      <div className="mb-4">
        <p className="font-heading text-sm font-semibold">Welcome — let&apos;s get you set up</p>
        <p className="text-muted-foreground text-sm">
          Upload the documents below. Your recruiter is notified as you go.
        </p>
      </div>

      {documents.length > 0 && (
        <>
          <div className="mb-4">
            <div className="mb-1 flex justify-between text-xs">
              <span className="text-muted-foreground">Documents collected</span>
              <span className="tabular-nums">
                {view.documents_received}/{view.documents_total}
              </span>
            </div>
            <div className="bg-muted h-2 overflow-hidden rounded-full">
              <div className="bg-primary h-full rounded-full" style={{ width: `${pct}%` }} />
            </div>
          </div>

          <ul className="mb-4 space-y-2">
            {documents.map((t) => (
              <li
                key={t.id}
                className="bg-muted/50 flex items-center justify-between gap-3 rounded-lg p-3"
              >
                <span className="flex items-center gap-2 text-sm">
                  {t.uploaded ? (
                    <CheckCircle2 className="size-4 text-emerald-500" />
                  ) : (
                    <FileUp className="text-muted-foreground size-4" />
                  )}
                  {t.label}
                </span>
                {t.uploaded ? (
                  <span className="text-xs text-emerald-600 dark:text-emerald-400">Received</span>
                ) : (
                  <label className="cursor-pointer">
                    <Button asChild size="sm" variant="outline" disabled={busy === t.id}>
                      <span>
                        {busy === t.id ? (
                          <Loader2 className="size-3.5 animate-spin" />
                        ) : (
                          <FileUp className="size-3.5" />
                        )}
                        Upload
                      </span>
                    </Button>
                    <input
                      type="file"
                      accept=".pdf,.docx,.txt,.md"
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
        <p className="mb-4 rounded-lg bg-emerald-500/10 p-3 text-sm text-emerald-600 dark:text-emerald-400">
          All documents received — you&apos;re all set. Welcome aboard!
        </p>
      )}

      {other.length > 0 && (
        <div>
          <p className="eyebrow mb-2">Your first week</p>
          <ul className="text-muted-foreground space-y-1 text-sm">
            {other.map((t) => (
              <li key={t.id}>• {t.label}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
