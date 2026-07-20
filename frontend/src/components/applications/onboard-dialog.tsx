"use client";

import * as React from "react";
import { Loader2, Rocket } from "lucide-react";
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
import type { OnboardingKit } from "@/lib/api/client";

export function OnboardDialog({ appId, name }: { appId: number; name: string }) {
  const [open, setOpen] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [kit, setKit] = React.useState<OnboardingKit | null>(null);

  async function generate() {
    setLoading(true);
    setKit(null);
    const res = await fetch(`/api/applications/${appId}/onboarding`, { method: "POST" });
    setLoading(false);
    if (!res.ok) {
      const err = await res.json().catch(() => null);
      toast.error(err?.detail ?? err?.error ?? `Failed (${res.status})`);
      return;
    }
    setKit((await res.json()) as OnboardingKit);
  }

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next && !kit && !loading) generate();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <button className="text-muted-foreground hover:text-foreground mt-2 inline-flex items-center gap-1 text-[10px] transition-colors">
          <Rocket className="size-3" /> Onboard
        </button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Onboarding kit</DialogTitle>
          <DialogDescription>
            First-week plan and checklist for <span className="font-medium">{name}</span>.
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="text-muted-foreground flex items-center justify-center gap-2 py-12 text-sm">
            <Loader2 className="size-4 animate-spin" /> Generating…
          </div>
        )}

        {kit && !loading && (
          <div className="space-y-5 py-2">
            {kit.welcome_message && (
              <p className="text-sm italic">{kit.welcome_message}</p>
            )}

            {kit.checklist.length > 0 && (
              <section>
                <p className="eyebrow mb-2">Setup checklist</p>
                <ul className="space-y-1 text-sm">
                  {kit.checklist.map((c, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="text-muted-foreground">☐</span> {c}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {kit.week_one_plan.length > 0 && (
              <section>
                <p className="eyebrow mb-2">Week one</p>
                <ul className="space-y-1.5 text-sm">
                  {kit.week_one_plan.map((t, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="text-primary min-w-14 font-medium">{t.when}</span>
                      <span>{t.task}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {kit.documents.length > 0 && (
              <section>
                <p className="eyebrow mb-2">Documents</p>
                <div className="flex flex-wrap gap-1.5">
                  {kit.documents.map((d, i) => (
                    <span key={i} className="bg-muted rounded-full px-2.5 py-1 text-xs">
                      {d}
                    </span>
                  ))}
                </div>
              </section>
            )}

            <Button type="button" variant="outline" onClick={generate} className="w-full">
              Regenerate
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
