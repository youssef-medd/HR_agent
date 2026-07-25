"use client";

import * as React from "react";
import { CalendarCheck, CheckCircle2, ExternalLink, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { BookingView } from "@/lib/api/client";

export function BookingPanel({ email, appId }: { email: string; appId: number }) {
  const [view, setView] = React.useState<BookingView | null>(null);
  const [slot, setSlot] = React.useState("");
  const [saving, setSaving] = React.useState(false);

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

  async function confirm() {
    setSaving(true);
    await fetch("/api/public/booking/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, application_id: appId, slot: slot.trim() || null }),
    });
    setSaving(false);
    setSlot("");
    setTimeout(load, 800);
  }

  if (!view) return null;

  if (view.booked) {
    return (
      <div className="surface flex flex-col items-center gap-2 p-6 text-center">
        <CheckCircle2 className="size-8 text-emerald-500" />
        <p className="font-medium">Interview scheduled</p>
        {view.when && <p className="text-muted-foreground text-sm">{view.when}</p>}
      </div>
    );
  }

  return (
    <div className="surface p-6">
      <div className="mb-3 flex items-center gap-2">
        <CalendarCheck className="text-primary size-5" />
        <p className="font-heading text-sm font-semibold">Book your interview</p>
      </div>
      <p className="text-muted-foreground mb-4 text-sm">
        Pick a time that works for you, then confirm below.
      </p>

      {view.link && (
        <Button asChild variant="outline" className="mb-4 w-full">
          <a href={view.link} target="_blank" rel="noreferrer">
            Open booking page <ExternalLink className="size-4" />
          </a>
        </Button>
      )}

      <div className="grid gap-2">
        <Label htmlFor="slot" className="text-xs">
          The slot you booked (optional)
        </Label>
        <Input
          id="slot"
          value={slot}
          onChange={(e) => setSlot(e.target.value)}
          placeholder="e.g. Tuesday 3pm"
        />
        <Button type="button" onClick={confirm} disabled={saving} className="mt-1">
          {saving ? <Loader2 className="size-4 animate-spin" /> : <CalendarCheck className="size-4" />}
          {saving ? "Confirming…" : "I've booked — confirm"}
        </Button>
      </div>
    </div>
  );
}
