"use client";

import * as React from "react";
import { Copy, Loader2, Radar } from "lucide-react";
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
import type { SourcingKit } from "@/lib/api/client";

function CopyButton({ text, label }: { text: string; label: string }) {
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(`${label} copied`);
    } catch {
      toast.error("Copy failed");
    }
  }
  return (
    <Button type="button" variant="ghost" size="sm" onClick={copy} className="h-7 gap-1 px-2 text-xs">
      <Copy className="size-3" /> Copy
    </Button>
  );
}

export function SourceDialog({ jobId, jobTitle }: { jobId: number; jobTitle: string }) {
  const [open, setOpen] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [kit, setKit] = React.useState<SourcingKit | null>(null);

  async function generate() {
    setLoading(true);
    setKit(null);
    const res = await fetch(`/api/jobs/${jobId}/sourcing`, { method: "POST" });
    setLoading(false);
    if (!res.ok) {
      const err = await res.json().catch(() => null);
      toast.error(err?.detail ?? err?.error ?? `Failed (${res.status})`);
      return;
    }
    setKit((await res.json()) as SourcingKit);
  }

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next && !kit && !loading) generate();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5">
          <Radar className="size-3.5" /> Source
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Sourcing kit</DialogTitle>
          <DialogDescription>
            Boolean search and outreach draft for <span className="font-medium">{jobTitle}</span>.
            Review and send manually.
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="text-muted-foreground flex items-center justify-center gap-2 py-12 text-sm">
            <Loader2 className="size-4 animate-spin" /> Generating…
          </div>
        )}

        {kit && !loading && (
          <div className="space-y-5 py-2">
            <section>
              <div className="mb-1 flex items-center justify-between">
                <p className="eyebrow">Boolean search</p>
                <CopyButton text={kit.boolean_search} label="Boolean search" />
              </div>
              <pre className="bg-muted overflow-x-auto rounded-lg p-3 text-xs whitespace-pre-wrap">
                {kit.boolean_search}
              </pre>
            </section>

            {kit.keywords.length > 0 && (
              <section>
                <p className="eyebrow mb-2">Keywords</p>
                <div className="flex flex-wrap gap-1.5">
                  {kit.keywords.map((k) => (
                    <span key={k} className="bg-muted rounded-full px-2.5 py-1 text-xs">
                      {k}
                    </span>
                  ))}
                </div>
              </section>
            )}

            {kit.platforms.length > 0 && (
              <section>
                <p className="eyebrow mb-2">Platforms</p>
                <p className="text-sm">{kit.platforms.join(" · ")}</p>
              </section>
            )}

            <section>
              <div className="mb-1 flex items-center justify-between">
                <p className="eyebrow">Outreach draft</p>
                <CopyButton
                  text={`${kit.outreach_subject}\n\n${kit.outreach_message}`}
                  label="Outreach"
                />
              </div>
              <p className="text-sm font-medium">{kit.outreach_subject}</p>
              <p className="text-muted-foreground mt-1 text-sm whitespace-pre-wrap">
                {kit.outreach_message}
              </p>
            </section>

            <Button type="button" variant="outline" onClick={generate} className="w-full">
              Regenerate
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
