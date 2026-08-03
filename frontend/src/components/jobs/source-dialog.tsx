"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Copy, Loader2, Radar, Upload, UserPlus } from "lucide-react";
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
import type { SourcedProfile, SourcingKit } from "@/lib/api/client";

const STATUS_TONE: Record<string, string> = {
  sourced: "bg-muted text-muted-foreground",
  contacted: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
  replied: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  imported: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
};

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
  // A2 sourced-people tracking
  const [sourced, setSourced] = React.useState<SourcedProfile[]>([]);
  const [newName, setNewName] = React.useState("");
  const [newUrl, setNewUrl] = React.useState("");
  const [adding, setAdding] = React.useState(false);
  const csvRef = React.useRef<HTMLInputElement>(null);
  const profileFileRef = React.useRef<HTMLInputElement>(null);
  const [uploadingProfile, setUploadingProfile] = React.useState(false);
  // Per-candidate outreach (spec §A2: personalised from the pasted profile)
  const [personal, setPersonal] = React.useState<SourcingKit["outreach"] | null>(null);
  const [drafting, setDrafting] = React.useState(false);

  async function importCsv(file: File) {
    const form = new FormData();
    form.set("file", file);
    const res = await fetch(`/api/jobs/${jobId}/sourced/import-csv`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      toast.error("CSV import failed");
      return;
    }
    const body = (await res.json()) as { added: number; skipped_duplicates: number };
    toast.success(`Added ${body.added} · skipped ${body.skipped_duplicates} already sourced`);
    loadSourced();
    if (csvRef.current) csvRef.current.value = "";
  }

  async function uploadProfile(file: File) {
    setUploadingProfile(true);
    const form = new FormData();
    form.set("file", file);
    if (importName.trim()) form.set("full_name", importName.trim());
    const res = await fetch(`/api/jobs/${jobId}/import-profile/upload`, {
      method: "POST",
      body: form,
    });
    setUploadingProfile(false);
    if (profileFileRef.current) profileFileRef.current.value = "";
    if (!res.ok) {
      const err = await res.json().catch(() => null);
      toast.error(err?.detail ?? "Could not read that file");
      return;
    }
    const body = await res.json();
    setImportName("");
    router.refresh();
    toast.success(`Imported as application #${body.application_id} — scoring now`);
  }

  async function draftOutreach() {
    if (!importText.trim()) {
      toast.error("Paste the profile first — the drafts are written from it");
      return;
    }
    setDrafting(true);
    setPersonal(null);
    const res = await fetch(`/api/jobs/${jobId}/outreach`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile_text: importText }),
    });
    setDrafting(false);
    if (!res.ok) {
      toast.error("Could not draft outreach");
      return;
    }
    setPersonal((await res.json()) as SourcingKit["outreach"]);
  }

  const loadSourced = React.useCallback(async () => {
    const res = await fetch(`/api/jobs/${jobId}/sourced`, { cache: "no-store" });
    if (res.ok) setSourced((await res.json()) as SourcedProfile[]);
  }, [jobId]);

  async function addSourced() {
    if (!newName.trim() && !newUrl.trim()) {
      toast.error("Add a name or a profile URL");
      return;
    }
    setAdding(true);
    const res = await fetch(`/api/jobs/${jobId}/sourced`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_name: newName, profile_url: newUrl || null }),
    });
    setAdding(false);
    if (res.status === 409) {
      toast.error("Already sourced for this job — don't contact them twice");
      return;
    }
    if (!res.ok) {
      toast.error("Could not add");
      return;
    }
    setNewName("");
    setNewUrl("");
    loadSourced();
  }

  async function markContacted(id: number) {
    const res = await fetch(`/api/jobs/sourced/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "contacted" }),
    });
    if (res.ok) loadSourced();
  }

  async function generate(refresh = false) {
    setLoading(true);
    setKit(null);
    const res = await fetch(`/api/jobs/${jobId}/sourcing${refresh ? "?refresh=true" : ""}`, {
      method: "POST",
    });
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
    if (next) {
      if (!kit && !loading) generate();
      loadSourced();
    }
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

            <Button
              type="button"
              variant="outline"
              onClick={() => generate(true)}
              className="w-full"
            >
              Regenerate
            </Button>
          </div>
        )}

        {/* Sourced people — the record that prevents contacting someone twice */}
        <section className="mt-2 border-t pt-4">
          <p className="eyebrow mb-2">Sourced people ({sourced.length})</p>
          <p className="text-muted-foreground mb-3 text-xs">
            Log each person you find, so nobody gets contacted twice.
          </p>

          <div className="mb-3 grid gap-2 sm:grid-cols-[1fr_1.4fr_auto]">
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Full name"
              className="h-9"
            />
            <Input
              value={newUrl}
              onChange={(e) => setNewUrl(e.target.value)}
              placeholder="linkedin.com/in/…"
              className="h-9"
            />
            <Button type="button" size="sm" onClick={addSourced} disabled={adding} className="h-9">
              {adding ? <Loader2 className="size-4 animate-spin" /> : "Add"}
            </Button>
          </div>

          <div className="mb-3">
            <input
              ref={csvRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) importCsv(f);
              }}
            />
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-8 gap-1.5 text-xs"
              onClick={() => csvRef.current?.click()}
            >
              <Upload className="size-3.5" /> Import CSV list
            </Button>
            <span className="text-muted-foreground ml-2 text-[11px]">
              columns: name, profile_url, notes — duplicates skipped
            </span>
          </div>

          {sourced.length > 0 && (
            <ul className="space-y-1.5">
              {sourced.map((p) => (
                <li
                  key={p.id}
                  className="bg-muted/50 flex items-center justify-between gap-2 rounded-lg p-2 text-sm"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium">{p.full_name || "—"}</p>
                    {p.profile_url && (
                      <a
                        href={p.profile_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-muted-foreground truncate text-xs hover:underline"
                      >
                        {p.profile_url}
                      </a>
                    )}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] capitalize ${STATUS_TONE[p.status] ?? "bg-muted"}`}
                    >
                      {p.status}
                    </span>
                    {p.status === "sourced" && (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-7 text-xs"
                        onClick={() => markContacted(p.id)}
                      >
                        Mark contacted
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

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
            <div className="mt-1 flex flex-wrap gap-2">
              <Button type="button" onClick={importProfile} disabled={importing} className="flex-1">
                {importing ? <Loader2 className="size-4 animate-spin" /> : <UserPlus className="size-4" />}
                {importing ? "Importing…" : "Import & score"}
              </Button>

              <input
                ref={profileFileRef}
                type="file"
                accept=".pdf,.docx,.txt,.md"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) uploadProfile(f);
                }}
              />
              <Button
                type="button"
                variant="outline"
                disabled={uploadingProfile}
                onClick={() => profileFileRef.current?.click()}
                className="gap-1.5"
              >
                {uploadingProfile ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Upload className="size-4" />
                )}
                Upload PDF export
              </Button>
            </div>
            <p className="text-muted-foreground text-[11px]">
              Or upload the profile PDF (LinkedIn → More → Save to PDF).
            </p>

            {/* Per-candidate outreach, written from the pasted profile */}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={draftOutreach}
              disabled={drafting}
              className="mt-1 gap-1.5"
            >
              {drafting ? <Loader2 className="size-4 animate-spin" /> : <Radar className="size-4" />}
              {drafting ? "Writing…" : "Draft outreach for this person"}
            </Button>

            {personal && personal.length > 0 && (
              <div className="grid gap-2">
                {personal.map((o, i) => (
                  <div key={i} className="rounded-xl border p-3">
                    <div className="mb-1 flex items-center justify-between">
                      <span className="chip bg-muted capitalize">{o.tone}</span>
                      <CopyButton text={`${o.subject}\n\n${o.message}`} label="Outreach" />
                    </div>
                    <p className="text-sm font-medium">{o.subject}</p>
                    <p className="text-muted-foreground mt-1 text-sm whitespace-pre-wrap">
                      {o.message}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </DialogContent>
    </Dialog>
  );
}
