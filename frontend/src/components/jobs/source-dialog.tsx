"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Copy, Loader2, Radar, UserPlus } from "lucide-react";
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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [kit, setKit] = React.useState<SourcingKit | null>(null);
  const [importText, setImportText] = React.useState("");
  const [importName, setImportName] = React.useState("");
  const [importing, setImporting] = React.useState(false);

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

  async function importProfile() {
    if (!importText.trim()) {
      toast.error("Paste a profile first");
      return;
    }
    setImporting(true);
    const res = await fetch(`/api/jobs/${jobId}/import-profile`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_text: importText, full_name: importName || null }),
    });
    setImporting(false);
    if (!res.ok) {
      const err = await res.json().catch(() => null);
      toast.error(err?.detail ?? err?.error ?? `Import failed (${res.status})`);
      return;
    }
    const body = await res.json();
    setImportText("");
    setImportName("");
    router.refresh();
    toast.success(`Imported as application #${body.application_id} — scoring now`);
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
            Search strings + outreach for <span className="font-medium">{jobTitle}</span>. Run the
            searches yourself, then paste a profile below to bring it into the pipeline.
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
              <p className="eyebrow mb-2">Search strings (ranked)</p>
              <ol className="space-y-1.5">
                {kit.search_strings.map((s, i) => (
                  <li key={i} className="bg-muted flex items-start gap-2 rounded-lg p-2 text-xs">
                    <span className="text-muted-foreground shrink-0">{i + 1}.</span>
                    <code className="min-w-0 flex-1 break-words">{s}</code>
                    <CopyButton text={s} label="Search" />
                  </li>
                ))}
              </ol>
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
              <p className="eyebrow mb-2">Outreach drafts</p>
              <div className="grid gap-2">
                {kit.outreach.map((o, i) => (
                  <div key={i} className="rounded-xl border p-3">
                    <div className="mb-1 flex items-center justify-between">
                      <span className="chip bg-muted capitalize">{o.tone}</span>
                      <CopyButton text={`${o.subject}\n\n${o.message}`} label="Outreach" />
                    </div>
                    <p className="text-sm font-medium">{o.subject}</p>
                    <p className="text-muted-foreground mt-1 text-sm whitespace-pre-wrap">{o.message}</p>
                  </div>
                ))}
              </div>
            </section>

            <Button type="button" variant="outline" onClick={generate} className="w-full">
              Regenerate
            </Button>
          </div>
        )}

        {/* Import a sourced profile — the "assist" half of A2 */}
        <section className="mt-2 border-t pt-4">
          <p className="eyebrow mb-2 flex items-center gap-1.5">
            <UserPlus className="size-3.5" /> Import a sourced profile
          </p>
          <p className="text-muted-foreground mb-3 text-xs">
            Paste the public profile text you found. It&apos;s parsed and scored like a CV, tagged{" "}
            <code>linkedin_assist</code>.
          </p>
          <div className="grid gap-2">
            <Label htmlFor="imp-name" className="text-xs">
              Name (optional)
            </Label>
            <Input
              id="imp-name"
              value={importName}
              onChange={(e) => setImportName(e.target.value)}
              placeholder="Candidate name"
            />
            <Label htmlFor="imp-text" className="text-xs">
              Profile text
            </Label>
            <Textarea
              id="imp-text"
              rows={5}
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              placeholder="Paste the profile summary, experience, skills…"
            />
            <Button type="button" onClick={importProfile} disabled={importing} className="mt-1">
              {importing ? <Loader2 className="size-4 animate-spin" /> : <UserPlus className="size-4" />}
              {importing ? "Importing…" : "Import & score"}
            </Button>
          </div>
        </section>
      </DialogContent>
    </Dialog>
  );
}
