"use client";

import * as React from "react";
import Link from "next/link";
import { ArrowLeft, Loader2, Search } from "lucide-react";

import { StateBadge } from "@/components/shell/state-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { TrackedApplication } from "@/lib/api/client";
import { type ApplicationState } from "@/lib/mocks/types";

function titleCase(s: string): string {
  const words = s.replaceAll("_", " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export default function PortalPage() {
  const [email, setEmail] = React.useState("");
  const [ref, setRef] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<TrackedApplication | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (loading) return;
    setError(null);
    setResult(null);
    setLoading(true);
    const res = await fetch(
      `/api/public/track?email=${encodeURIComponent(email.trim())}&application_id=${encodeURIComponent(ref.trim())}`,
      { cache: "no-store" },
    );
    setLoading(false);
    if (!res.ok) {
      setError("No application found for that email and reference. Check both and try again.");
      return;
    }
    setResult((await res.json()) as TrackedApplication);
  }

  return (
    <main className="mx-auto max-w-xl px-6 py-16">
      <Link
        href="/apply"
        className="text-muted-foreground hover:text-foreground mb-6 inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" /> Open roles
      </Link>

      <header className="mb-8">
        <p className="text-primary text-sm font-medium">Welyne · Candidate portal</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Track your application</h1>
        <p className="text-muted-foreground mt-2">
          Enter the email you applied with and your application reference number.
        </p>
      </header>

      <Card className="mb-8">
        <CardContent className="pt-6">
          <form onSubmit={onSubmit} className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="jane@example.com"
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="ref">Application reference (#)</Label>
              <Input
                id="ref"
                inputMode="numeric"
                required
                value={ref}
                onChange={(e) => setRef(e.target.value)}
                placeholder="e.g. 12"
              />
            </div>
            <Button type="submit" disabled={loading} className="mt-1">
              {loading ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
              {loading ? "Looking up…" : "Track"}
            </Button>
            {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
          </form>
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-4">
            <CardTitle className="text-base">
              {result.job_title ?? "Your application"}{" "}
              <span className="text-muted-foreground font-normal">· #{result.id}</span>
            </CardTitle>
            <StateBadge state={result.state as ApplicationState} />
          </CardHeader>
          <CardContent>
            <p className="eyebrow mb-3">Progress</p>
            {result.timeline.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                Received on {result.created_at.slice(0, 10)} — processing will begin shortly.
              </p>
            ) : (
              <ol className="relative ml-1 border-l pl-5">
                {result.timeline.map((t, i) => (
                  <li key={i} className="mb-4 last:mb-0">
                    <span className="bg-primary absolute -left-[5px] mt-1.5 size-2.5 rounded-full" />
                    <p className="text-sm font-medium">{titleCase(t.state)}</p>
                    <p className="text-muted-foreground text-xs">
                      {new Date(t.at).toLocaleString()}
                    </p>
                  </li>
                ))}
              </ol>
            )}
          </CardContent>
        </Card>
      )}
    </main>
  );
}
