import Link from "next/link";
import { ArrowRight, Briefcase, MapPin } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { API_URL } from "@/lib/api/client";

export const dynamic = "force-dynamic";

interface PublicJob {
  id: number;
  title: string;
  department: string | null;
  location: string | null;
  description: string;
}

async function getOpenJobs(): Promise<PublicJob[]> {
  try {
    const res = await fetch(`${API_URL}/public/jobs`, { cache: "no-store" });
    if (!res.ok) return [];
    return (await res.json()) as PublicJob[];
  } catch {
    return [];
  }
}

export default async function ApplyIndexPage() {
  const jobs = await getOpenJobs();

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <header className="mb-10">
        <p className="text-primary text-sm font-medium">Welyne · Careers</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Open roles</h1>
        <p className="text-muted-foreground mt-2">
          Pick a role and submit your CV — no account needed. We&apos;ll review it and be in touch.
        </p>
      </header>

      {jobs.length === 0 ? (
        <Card>
          <CardContent className="text-muted-foreground py-12 text-center text-sm">
            No open roles right now. Please check back soon.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4">
          {jobs.map((job) => (
            <Card key={job.id} className="transition-shadow hover:shadow-md">
              <CardHeader>
                <CardTitle className="text-lg">{job.title}</CardTitle>
                <CardDescription className="flex flex-wrap gap-x-4 gap-y-1">
                  {job.department && (
                    <span className="inline-flex items-center gap-1">
                      <Briefcase className="size-3.5" /> {job.department}
                    </span>
                  )}
                  {job.location && (
                    <span className="inline-flex items-center gap-1">
                      <MapPin className="size-3.5" /> {job.location}
                    </span>
                  )}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex items-center justify-between gap-4">
                <p className="text-muted-foreground line-clamp-2 text-sm">
                  {job.description || "No description provided."}
                </p>
                <Button asChild>
                  <Link href={`/apply/${job.id}`}>
                    Apply <ArrowRight className="size-4" />
                  </Link>
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </main>
  );
}
