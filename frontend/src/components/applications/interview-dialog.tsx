"use client";

/**
 * A6 recruiter controls for a booked interview: see the slot and the replan
 * history, move it to another time, or record the outcome (attended / no-show).
 * Every action writes through the API, which re-issues the calendar invite and
 * keeps the attention queue in sync.
 */

import * as React from "react";
import { CalendarClock, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { InterviewView } from "@/lib/api/client";

const HISTORY_LABEL: Record<string, string> = {
  picked: "Slot picked",
  rescheduled: "Rescheduled",
  cancelled: "Cancelled",
  no_show: "No-show",
  attended: "Attended",
};

function fmt(iso: string | null | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

/** `datetime-local` wants a local-time string with no zone suffix. */
function toLocalInput(iso: string | null): string {
  const d = iso ? new Date(iso) : new Date(Date.now() + 24 * 3600 * 1000);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function InterviewDialog({ appId, name }: { appId: number; name: string }) {
  const [open, setOpen] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [view, setView] = React.useState<InterviewView | null>(null);
  const [start, setStart] = React.useState("");

  const load = React.useCallback(async () => {
    setLoading(true);
    const res = await fetch(`/api/applications/${appId}/interview`, { cache: "no-store" });
    setLoading(false);
    if (!res.ok) {
      toast.error(`Could not load the interview (${res.status})`);
      return;
    }
    const data = (await res.json()) as InterviewView;
    setView(data);
    setStart(toLocalInput(data.scheduled_at));
  }, [appId]);

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next) load();
  }

  async function act(action: string, body?: Record<string, unknown>) {
    setBusy(true);
    const res = await fetch(`/api/applications/${appId}/interview/${action}`, {
      method: "POST",
      ...(body
        ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
        : {}),
    });
    setBusy(false);
    if (!res.ok) {
      const err = (await res.json().catch(() => null)) as { detail?: string; error?: string } | null;
      toast.error(err?.detail ?? err?.error ?? `Failed (${res.status})`);
      return;
    }
    const data = (await res.json()) as InterviewView;
    setView(data);
    setStart(toLocalInput(data.scheduled_at));
    toast.success(
      action === "reschedule"
        ? "Interview moved — updated invite sent"
        : action === "no-show"
          ? "No-show recorded"
          : action === "attended"
            ? "Marked as attended"
            : "Interview cancelled",
    );
  }

  function reschedule() {
    if (!start) {
      toast.error("Pick a new date and time first");
      return;
    }
    // `datetime-local` has no zone; the recruiter means their own local time.
    act("reschedule", { start: new Date(start).toISOString() });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <button className="text-muted-foreground hover:text-foreground mt-2 inline-flex items-center gap-1 text-[10px] transition-colors">
          <CalendarClock className="size-3" /> Interview
        </button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Interview</DialogTitle>
          <DialogDescription>
            Slot, replan history and outcome for <span className="font-medium">{name}</span>.
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="text-muted-foreground flex items-center justify-center gap-2 py-12 text-sm">
            <Loader2 className="size-4 animate-spin" /> Loading…
          </div>
        )}

        {view && !loading && (
          <div className="space-y-5 py-1">
            <section className="bg-muted/40 rounded-2xl p-4">
              <p className="eyebrow mb-1">Scheduled</p>
              <p className="text-sm font-medium">{view.when ?? fmt(view.scheduled_at)}</p>
              <p className="text-muted-foreground mt-1 text-xs">
                {view.timezone}
                {view.reminder_sent ? " · reminder sent" : ""}
                {view.reschedule_count > 0
                  ? ` · rescheduled ${view.reschedule_count}×`
                  : ""}
              </p>
              {view.no_show && (
                <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
                  Marked as a no-show — reschedule or decline.
                </p>
              )}
              {view.outcome === "attended" && (
                <p className="mt-2 text-xs text-emerald-600 dark:text-emerald-400">
                  Candidate attended.
                </p>
              )}
            </section>

            <section className="space-y-2">
              <p className="eyebrow">Move the interview</p>
              <Input
                type="datetime-local"
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
              <Button
                type="button"
                onClick={reschedule}
                disabled={busy}
                className="w-full"
              >
                {busy ? <Loader2 className="size-4 animate-spin" /> : null}
                Reschedule &amp; resend invite
              </Button>
            </section>

            <section className="grid grid-cols-3 gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => act("attended")}
              >
                Attended
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => act("no-show")}
              >
                No-show
              </Button>
              <Button
                type="button"
                variant="destructive"
                size="sm"
                disabled={busy}
                onClick={() => act("cancel", { reason: null })}
              >
                Cancel
              </Button>
            </section>

            {view.history.length > 0 && (
              <section>
                <p className="eyebrow mb-2">History</p>
                <ul className="space-y-1.5 text-xs">
                  {[...view.history].reverse().map((h, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="text-muted-foreground min-w-28">{fmt(h.at)}</span>
                      <span>
                        {HISTORY_LABEL[h.kind] ?? h.kind}
                        {h.slot ? ` → ${fmt(h.slot)}` : ""}
                        {h.source ? ` · ${h.source}` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
