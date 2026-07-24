"use client";

import * as React from "react";
import Link from "next/link";
import { CheckCircle2, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const ACCEPT = ".pdf,.docx,.txt,.md";

export function ApplyForm({ jobId, jobTitle }: { jobId: number; jobTitle: string }) {
  const [pending, setPending] = React.useState(false);
  const [done, setDone] = React.useState(false);
  const [appId, setAppId] = React.useState<number | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending) return;

    const form = e.currentTarget;
    const data = new FormData(form);
    data.set("job_id", String(jobId));

    const file = data.get("file") as File | null;
    if (!file || file.size === 0) {
      toast.error("Attach your CV first");
      return;
    }
    const email = String(data.get("email") ?? "").trim();
    if (!email) {
      toast.error("Enter your email");
      return;
    }

    setPending(true);
    const res = await fetch("/api/public/apply", { method: "POST", body: data });
    setPending(false);

    if (!res.ok) {
      const err = await res.json().catch(() => null);
      toast.error(err?.detail ?? err?.error ?? `Submission failed (${res.status})`);
      return;
    }

    const body = await res.json().catch(() => null);
    setAppId(typeof body?.application_id === "number" ? body.application_id : null);
    setDone(true);
  }

  if (done) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        <CheckCircle2 className="size-10 text-emerald-500" />
        <p className="font-medium">Application received</p>
        <p className="text-muted-foreground text-sm">
          Thanks for applying to <span className="font-medium">{jobTitle}</span>. Our team will
          review your CV and reach out.
        </p>
        {appId !== null && (
          <p className="text-muted-foreground text-sm">
            Your reference is <span className="text-foreground font-semibold">#{appId}</span> — track
            your status any time at{" "}
            <Link href="/portal" className="text-primary underline">
              the candidate portal
            </Link>
            .
          </p>
        )}
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-4">
      <div className="grid gap-2">
        <Label htmlFor="full_name">Full name</Label>
        <Input id="full_name" name="full_name" placeholder="Jane Doe" autoComplete="name" />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          name="email"
          type="email"
          required
          placeholder="jane@example.com"
          autoComplete="email"
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="phone">WhatsApp number (optional)</Label>
        <Input
          id="phone"
          name="phone"
          type="tel"
          placeholder="+216 12 345 678"
          autoComplete="tel"
        />
        <p className="text-muted-foreground text-xs">
          If shortlisted, our assistant may pre-screen you on WhatsApp.
        </p>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="file">CV</Label>
        <Input id="file" name="file" type="file" accept={ACCEPT} required />
        <p className="text-muted-foreground text-xs">PDF, DOCX, TXT or MD · max 10 MB</p>
      </div>
      <Button type="submit" disabled={pending} className="mt-2">
        {pending && <Loader2 className="size-4 animate-spin" />}
        {pending ? "Submitting…" : "Submit application"}
      </Button>
    </form>
  );
}
