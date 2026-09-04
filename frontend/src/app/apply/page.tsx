import { JobSearch, type PublicJob } from "@/components/apply/job-search";
import { PublicShell } from "@/components/apply/public-shell";
import { API_URL } from "@/lib/api/client";

export const dynamic = "force-dynamic";

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
    <PublicShell>
      <header className="mx-auto mt-8 mb-8 max-w-2xl text-center">
        <p className="text-primary text-sm font-medium tracking-wide">
          Welyne · Careers
        </p>
        <h1 className="font-heading mt-2 text-4xl font-semibold tracking-tight text-white sm:text-5xl">
          Open roles
        </h1>
        <p className="mt-3 text-sm text-white/50">
          Pick a role and submit your CV — no account needed. We&apos;ll review it and
          be in touch.
        </p>
      </header>

      <JobSearch jobs={jobs} />
    </PublicShell>
  );
}
