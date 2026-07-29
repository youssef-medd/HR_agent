"use client";

import * as React from "react";
import { BarChart3, Loader2, Quote } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { ApplicationView, ScoreCard } from "@/lib/api/client";

const SUBSCORES: { key: keyof ScoreCard; label: string }[] = [
  { key: "experience_match", label: "Experience" },
  { key: "skills_match", label: "Skills" },
  { key: "education_match", label: "Education" },
  { key: "sector_context_fit", label: "Sector & context" },
];

function Bar({ value }: { value: number }) {
  return (
    <div className="bg-muted relative h-2 w-full overflow-hidden rounded-full">
      <div
        className={`absolute inset-y-0 left-0 rounded-full ${value >= 70 ? "bg-primary" : "bg-muted-foreground/50"}`}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

export function ScoreCardDialog({ appId, name }: { appId: number; name: string }) {
  const [open, setOpen] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [score, setScore] = React.useState<ScoreCard | null>(null);

  async function load() {
    setLoading(true);
    const res = await fetch(`/api/applications/${appId}`, { cache: "no-store" });
    setLoading(false);
    if (res.ok) setScore(((await res.json()) as ApplicationView).score);
  }

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next && !score && !loading) load();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" className="mt-2 h-7 w-full gap-1 px-2 text-xs">
          <BarChart3 className="size-3.5" /> View score
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Score · {name}</DialogTitle>
          <DialogDescription>
            A4 ScoreCard — sub-scores, evidence, and provenance.
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="flex justify-center py-10">
            <Loader2 className="text-muted-foreground size-6 animate-spin" />
          </div>
        )}

        {!loading && !score && (
          <p className="text-muted-foreground py-8 text-center text-sm">
            No score yet for this application.
          </p>
        )}

        {score && (
          <div className="space-y-5">
            <div className="flex items-center gap-3">
              <span className="text-3xl font-semibold tabular-nums">{score.overall}</span>
              <span className="text-muted-foreground text-sm">/ 100</span>
              <span className="bg-muted ml-auto rounded-full px-2.5 py-1 text-xs font-medium capitalize">
                {score.recommendation}
              </span>
            </div>

            <div className="space-y-2.5">
              {SUBSCORES.map(({ key, label }) => {
                const v = (score[key] as number) ?? 0;
                return (
                  <div key={key} className="grid grid-cols-[9rem_1fr_2rem] items-center gap-3">
                    <span className="text-sm">{label}</span>
                    <Bar value={v} />
                    <span className="text-right text-xs tabular-nums">{v}</span>
                  </div>
                );
              })}
            </div>

            {score.rationale && (
              <p className="text-muted-foreground border-l-2 pl-3 text-sm">{score.rationale}</p>
            )}

            {score.hard_filter_failures && score.hard_filter_failures.length > 0 && (
              <div className="rounded-xl bg-red-500/10 p-3 text-sm text-red-600 dark:text-red-400">
                <p className="font-medium">Hard-filter failures</p>
                <ul className="mt-1 list-disc pl-5">
                  {score.hard_filter_failures.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              </div>
            )}

            {score.evidence && score.evidence.length > 0 && (
              <details open className="group">
                <summary className="cursor-pointer text-sm font-medium">
                  Evidence ({score.evidence.length})
                </summary>
                <ul className="mt-2 space-y-2">
                  {score.evidence.map((e, i) => (
                    <li key={i} className="bg-muted/60 rounded-lg p-2.5 text-sm">
                      <span className="text-muted-foreground mb-1 flex items-center gap-1 text-[10px] uppercase tracking-wide">
                        <Quote className="size-3" /> {e.dimension.replace(/_/g, " ")}
                      </span>
                      <span className="italic">&ldquo;{e.quote}&rdquo;</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}

            {score.semantic && (
              <p className="text-muted-foreground text-xs">
                Semantic pre-rank: {(score.semantic.prerank_score * 100).toFixed(0)}% (skills{" "}
                {(score.semantic.skills_sim * 100).toFixed(0)}%, experience{" "}
                {(score.semantic.experience_sim * 100).toFixed(0)}%)
              </p>
            )}

            {score.provenance && (
              <p className="text-muted-foreground border-t pt-3 text-[10px]">
                {score.provenance.model || "model"} · {score.provenance.prompt_version} · seed{" "}
                {score.provenance.run_seed}
              </p>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
