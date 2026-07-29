"use client";

import * as React from "react";
import { Loader2, MessageSquareText, Printer } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { ApplicationView, PrescreenBlock } from "@/lib/api/client";

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Open a printable window the recruiter can save as PDF (spec §A5). */
function printPrescreen(name: string, block: PrescreenBlock) {
  const rows = (block.transcript ?? [])
    .map(
      (m) =>
        `<p class="${m.role}"><b>${m.role === "assistant" ? "Assistant" : "Candidate"}:</b> ${esc(m.text)}</p>`,
    )
    .join("");
  const slots = Object.entries(block.slots ?? {})
    .filter(([, v]) => v)
    .map(([k, v]) => `<li><b>${esc(k.replace(/_/g, " "))}:</b> ${esc(v)}</li>`)
    .join("");
  const win = window.open("", "_blank", "width=800,height=900");
  if (!win) return;
  win.document.write(`<!doctype html><html><head><title>Pre-screening — ${esc(name)}</title>
    <style>body{font:14px/1.6 system-ui,sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem}
    h1{font-size:20px}h2{font-size:15px;margin-top:1.5rem}.assistant{color:#374151}.user{color:#111}
    .muted{color:#6b7280}</style></head><body>
    <h1>Pre-screening — ${esc(name)}</h1>
    ${block.summary ? `<h2>Summary</h2><p>${esc(block.summary)}</p>` : ""}
    ${slots ? `<h2>Details</h2><ul>${slots}</ul>` : ""}
    <h2>Transcript</h2>${rows || "<p class='muted'>No transcript.</p>"}
    </body></html>`);
  win.document.close();
  win.focus();
  win.print();
}

function FlagList({ title, items, tone }: { title: string; items?: string[]; tone: string }) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <p className={`text-xs font-medium ${tone}`}>{title}</p>
      <ul className="text-muted-foreground list-disc pl-5 text-sm">
        {items.map((f, i) => (
          <li key={i}>{f}</li>
        ))}
      </ul>
    </div>
  );
}

export function PrescreenDialog({ appId, name }: { appId: number; name: string }) {
  const [open, setOpen] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [block, setBlock] = React.useState<PrescreenBlock | null>(null);

  async function load() {
    setLoading(true);
    const res = await fetch(`/api/applications/${appId}`, { cache: "no-store" });
    setLoading(false);
    if (res.ok) setBlock(((await res.json()) as ApplicationView).prescreen);
  }

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next && !block && !loading) load();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" className="mt-2 h-7 w-full gap-1 px-2 text-xs">
          <MessageSquareText className="size-3.5" /> Pre-screen
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Pre-screening · {name}</DialogTitle>
          <DialogDescription>A5 recap — summary, details, flags, transcript.</DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="flex justify-center py-10">
            <Loader2 className="text-muted-foreground size-6 animate-spin" />
          </div>
        )}

        {!loading && !block && (
          <p className="text-muted-foreground py-8 text-center text-sm">
            No pre-screening for this application yet.
          </p>
        )}

        {block && (
          <div className="space-y-4">
            {block.summary && (
              <p className="text-muted-foreground border-l-2 pl-3 text-sm whitespace-pre-line">
                {block.summary}
              </p>
            )}

            {block.slots && Object.values(block.slots).some(Boolean) && (
              <ul className="grid grid-cols-2 gap-1 text-sm">
                {Object.entries(block.slots)
                  .filter(([, v]) => v)
                  .map(([k, v]) => (
                    <li key={k}>
                      <span className="text-muted-foreground capitalize">
                        {k.replace(/_/g, " ")}:
                      </span>{" "}
                      {v}
                    </li>
                  ))}
              </ul>
            )}

            <FlagList title="Great signals" items={block.flags?.great_signals} tone="text-emerald-600" />
            <FlagList title="Contradictions vs CV" items={block.flags?.contradictions} tone="text-amber-600" />
            <FlagList title="Red flags" items={block.flags?.red_flags} tone="text-red-600" />

            {block.transcript && block.transcript.length > 0 && (
              <details className="group">
                <summary className="cursor-pointer text-sm font-medium">
                  Transcript ({block.transcript.length})
                </summary>
                <div className="mt-2 space-y-1.5">
                  {block.transcript.map((m, i) => (
                    <p key={i} className="text-sm">
                      <span className="text-muted-foreground">
                        {m.role === "assistant" ? "Assistant" : "Candidate"}:
                      </span>{" "}
                      {m.text}
                    </p>
                  ))}
                </div>
              </details>
            )}

            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full gap-1"
              onClick={() => printPrescreen(name, block)}
            >
              <Printer className="size-4" /> Print / Save as PDF
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
