"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Loader2, Plus } from "lucide-react";
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
import { Textarea } from "@/components/ui/textarea";
import type { JobView } from "@/lib/api/client";

export function CreateJobDialog() {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [pending, setPending] = React.useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending) return;

    const form = e.currentTarget;
    const data = new FormData(form);

    setPending(true);
    const res = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: data.get("title"),
        department: data.get("department") || null,
        location: data.get("location") || null,
        description: data.get("description") || "",
        status: "published",
      }),
    });
    setPending(false);

    if (!res.ok) {
      const err = await res.json().catch(() => null);
      toast.error(err?.detail?.[0]?.msg ?? err?.error ?? `Create failed (${res.status})`);
      return;
    }

    const job = (await res.json()) as JobView;
    setOpen(false);
    form.reset();
    router.refresh();
    toast.success(`Job #${job.id} “${job.title}” published`);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="size-4" />
          New job
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>Create a job posting</DialogTitle>
            <DialogDescription>
              The description is what the judge (A4) scores every CV against — put the
              real requirements in it.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="title">Title</Label>
              <Input id="title" name="title" placeholder="AI Engineer" required minLength={3} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="department">Department (optional)</Label>
                <Input id="department" name="department" placeholder="Engineering" />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="location">Location (optional)</Label>
                <Input id="location" name="location" placeholder="Tunis, hybrid" />
              </div>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="description">Description & requirements</Label>
              <Textarea
                id="description"
                name="description"
                rows={8}
                placeholder={"Mission, must-have skills, nice-to-haves…"}
              />
            </div>
          </div>

          <DialogFooter>
            <Button type="submit" disabled={pending}>
              {pending && <Loader2 className="size-4 animate-spin" />}
              {pending ? "Publishing…" : "Publish job"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
