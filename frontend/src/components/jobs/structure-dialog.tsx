"use client";

import * as React from "react";
import { Check, Copy, Loader2, Sparkles } from "lucide-react";
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
import type { JobIntake } from "@/lib/api/client";

function Chips({ items }: { items: string[] }) {
  if (items.length === 0) return <span className="text-muted-foreground text-xs">—</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((s, i) => (
        <span key={i} className="bg-muted rounded-full px-2.5 py-1 text-xs">
          {s}
        </span>
      ))}
    </div>
  );
}

function CopyBlock({ label, text }: { label: string; text: string }) {
  const [copied, setCopied] = React.useState(false);
  async function copy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }
  return (
    <div className="rounded-xl border p-3">
      <div className="mb-1.5 flex items-center justify-between">
        <p className="text-xs font-medium">{label}</p>
        <button onClick={copy} className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs">
          {copied ? <Check className="size-3.5 text-emerald-500" /> : <Copy className="size-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <p className="text-muted-foreground text-xs whitespace-pre-wrap">{text || "—"}</p>
    </div>
  );
}

export function StructureDialog({ jobId, jobTitle }: { jobId: number; jobTitle: string }) {
  const [open, setOpen] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [data, setData] = React.useState<JobIntake | null>(null);

  async function run() {
    setLoading(true);
    setData(null);
    const res = await fetch(`/api/jobs/${jobId}/structure`, { method: "POST" });
    setLoading(false);
    if (!res.ok) {
      const err = await res.json().catch(() => null);
      toast.error(err?.detail ?? err?.error ?? `Failed (${res.status})`);
      return;
    }
    setData((await res.json()) as JobIntake);
  }

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next && !data && !loading) run();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5">
          <Sparkles className="size-3.5" /> Structure with AI
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Structured job spec</DialogTitle>
          <DialogDescription>
            A1 turned <span className="font-medium">{jobTitle}</span> into a JobSpec, scoring weights and
            channel posts.
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="text-muted-foreground flex items-center justify-center gap-2 py-12 text-sm">
            <Loader2 className="size-4 animate-spin" /> Structuring…
          </div>
        )}

        {data && !loading && (
          <div className="space-y-5 py-2 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <div><p className="eyebrow mb-1">Seniority</p>{data.spec.seniority || "—"}</div>
              <div><p className="eyebrow mb-1">Location</p>{data.spec.location || "—"}</div>
              <div className="col-span-2"><p className="eyebrow mb-1">Salary range</p>{data.spec.salary_range || "—"}</div>
            </div>

            <div><p className="eyebrow mb-2">Missions</p>
              <ul className="list-disc space-y-0.5 pl-5 text-sm">{data.spec.missions.map((m, i) => <li key={i}>{m}</li>)}</ul>
            </div>
            <div><p className="eyebrow mb-2">Must have</p><Chips items={data.spec.must_have} /></div>
            <div><p className="eyebrow mb-2">Nice to have</p><Chips items={data.spec.nice_to_have} /></div>
            <div><p className="eyebrow mb-2">Languages</p><Chips items={data.spec.languages} /></div>
            <div>
              <p className="eyebrow mb-2">Eliminatory criteria (hard filters)</p>
              <Chips items={data.spec.eliminatory_criteria} />
            </div>

            <div>
              <p className="eyebrow mb-2">Scoring weights</p>
              <div className="flex gap-4 text-xs">
                <span>Skills <b>{data.weights.skills}</b></span>
                <span>Experience <b>{data.weights.experience}</b></span>
                <span>Education <b>{data.weights.education}</b></span>
              </div>
            </div>

            <div>
              <p className="eyebrow mb-2">Channel posts</p>
              <div className="grid gap-2">
                <CopyBlock label="LinkedIn" text={data.channels.linkedin_post} />
                <CopyBlock label="Job board" text={data.channels.job_board_text} />
                <CopyBlock label="Careers page" text={data.channels.careers_page} />
                <CopyBlock label="WhatsApp" text={data.channels.whatsapp_blurb} />
              </div>
            </div>

            <Button type="button" variant="outline" onClick={run} className="w-full">
              Regenerate
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
