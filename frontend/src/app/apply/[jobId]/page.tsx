import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Briefcase, MapPin } from "lucide-react";

import { ApplyForm } from "@/components/apply/apply-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API_URL } from "@/lib/api/client";

export const dynamic = "force-dynamic";

interface PublicJob {
  id: number;
  title: string;
  department: string | null;
  location: string | null;
  description: string;
}

async function getJob(jobId: string): Promise<PublicJob | null> {
  try {
    const res = await fetch(`${API_URL}/public/jobs/${jobId}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as PublicJob;
  } catch {
    return null;
  }
}

export default async function ApplyJobPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  const job = await getJob(jobId);
  if (!job) notFound();

  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <Link
        href="/apply"
        className="text-muted-foreground hover:text-foreground mb-6 inline-flex items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" /> All roles
      </Link>

      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">{job.title}</h1>
        <div className="text-muted-foreground mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm">
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
        </div>
      </header>

      {job.description && (
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="text-base">About the role</CardTitle>
          </CardHeader>
          <CardContent className="text-muted-foreground text-sm whitespace-pre-wrap">
            {job.description}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Submit your application</CardTitle>
        </CardHeader>
        <CardContent>
          <ApplyForm jobId={job.id} jobTitle={job.title} />
        </CardContent>
      </Card>
    </main>
  );
}
