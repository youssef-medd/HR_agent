"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2, PencilLine, Plus, Sparkles } from "lucide-react";
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

import { AiIntakeChat } from "./ai-intake-chat";

type Choice = null | "manual" | "ai";

export function CreateJobDialog() {
  const router = useRouter();
  const [open, setOpen] = React.useState(false);
  const [choice, setChoice] = React.useState<Choice>(null);
  const [pending, setPending] = React.useState(false);

  function reset() {
    setChoice(null);
  }

  function close() {
    setOpen(false);
    setTimeout(reset, 200);
    router.refresh();
  }

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
    form.reset();
    toast.success(`Job #${job.id} “${job.title}” published`);
    close();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setTimeout(reset, 200);
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <Plus className="size-4" />
          New job
        </Button>
      </DialogTrigger>
      <DialogContent className={choice === "ai" ? "sm:max-w-2xl" : "sm:max-w-lg"}>
        {/* Step 0 — choose how to create */}
        {choice === null && (
          <>
            <DialogHeader>
              <DialogTitle>Create a job posting</DialogTitle>
              <DialogDescription>
                Fill it in yourself, or chat with the AI and let it draft everything for your review.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-3 py-2 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => setChoice("ai")}
                className="hover:border-primary group rounded-2xl border p-5 text-left transition-colors"
              >
                <Sparkles className="text-primary mb-2 size-6" />
                <p className="font-medium">Create with AI</p>
                <p className="text-muted-foreground mt-1 text-xs">
                  Describe the role in a chat — the AI asks a few questions, then drafts the full spec,
                  weights and posts. You confirm before it saves.
                </p>
              </button>
              <button
                type="button"
                onClick={() => setChoice("manual")}
                className="hover:border-primary rounded-2xl border p-5 text-left transition-colors"
              >
                <PencilLine className="text-muted-foreground mb-2 size-6" />
                <p className="font-medium">Fill in manually</p>
                <p className="text-muted-foreground mt-1 text-xs">
                  Enter the title and description yourself. You can still structure it with AI
                  afterwards from the job card.
                </p>
              </button>
            </div>
          </>
        )}

        {/* AI conversational intake */}
        {choice === "ai" && (
          <>
            <DialogHeader>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={reset}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <ArrowLeft className="size-4" />
                </button>
                <DialogTitle>Create with AI</DialogTitle>
              </div>
              <DialogDescription>
                Chat with the assistant. When it has enough, it proposes the job for you to save.
              </DialogDescription>
            </DialogHeader>
            <AiIntakeChat onCreated={() => close()} />
          </>
        )}

        {/* Manual form */}
        {choice === "manual" && (
          <form onSubmit={onSubmit}>
            <DialogHeader>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={reset}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <ArrowLeft className="size-4" />
                </button>
                <DialogTitle>Create a job posting</DialogTitle>
              </div>
              <DialogDescription>
                The description is what the judge (A4) scores every CV against — put the real
                requirements in it.
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
                <Label htmlFor="description">Description &amp; requirements</Label>
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
        )}
      </DialogContent>
    </Dialog>
  );
}
