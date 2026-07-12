"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Loader2, Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ApplicationCreated, ApplicationView } from "@/lib/api/client";

const ACCEPT = ".pdf,.docx,.txt,.md";

/** Poll GET /api/applications/{id} until it leaves RECEIVED (parse done) or times out. */
async function pollParsed(id: number, tries = 8): Promise<ApplicationView | null> {
  for (let i = 0; i < tries; i++) {
    const res = await fetch(`/api/applications/${id}`, { cache: "no-store" });
    if (res.ok) {
      const view = (await res.json()) as ApplicationView;
      if (view.cv || view.state !== "RECEIVED") return view;
    }
    await new Promise((r) => setTimeout(r, 1500));
  }
  return null;
}

export function UploadCvDialog() {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [pending, setPending] = React.useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending) return;

    const form = e.currentTarget;
    const data = new FormData(form);
    const file = data.get("file") as File | null;
    if (!file || file.size === 0) {
      toast.error("Choose a CV file first");
      return;
    }

    setPending(true);
    const res = await fetch("/api/applications", { method: "POST", body: data });

    if (!res.ok) {
      const err = await res.json().catch(() => null);
      setPending(false);
      toast.error(err?.detail ?? err?.error ?? `Upload failed (${res.status})`);
      return;
    }

    const created = (await res.json()) as ApplicationCreated;
    setOpen(false);
    setPending(false);
    form.reset();
    router.refresh();

    toast.promise(pollParsed(created.application_id), {
      loading: `Application #${created.application_id} received — parsing CV…`,
      success: (view) => {
        router.refresh();
        if (!view) return `Application #${created.application_id} queued.`;
        const name = view.cv?.full_name?.trim();
        return name
          ? `Parsed: ${name} — now ${view.state}`
          : `Application #${created.application_id} is now ${view.state}`;
      },
      error: "Could not confirm parse status",
    });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Upload className="size-4" />
          Upload CV
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>Upload a CV</DialogTitle>
            <DialogDescription>
              Creates an application and runs it through the orchestrator (parse → score).
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="job_id">Job ID</Label>
              <Input id="job_id" name="job_id" type="number" defaultValue={1} min={1} required />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="candidate_ref">Candidate reference (optional)</Label>
              <Input id="candidate_ref" name="candidate_ref" placeholder="email or name" />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="file">CV file</Label>
              <Input id="file" name="file" type="file" accept={ACCEPT} required />
              <p className="text-muted-foreground text-xs">PDF, DOCX, TXT or MD · max 10 MB</p>
            </div>
          </div>

          <DialogFooter>
            <Button type="submit" disabled={pending}>
              {pending && <Loader2 className="size-4 animate-spin" />}
              {pending ? "Uploading…" : "Upload"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
