import { PageHeader } from "@/components/shell/page-header";
import { type ApplicationSummary } from "@/lib/api/client";
import { apiGet } from "@/lib/api/server";
import { cn } from "@/lib/utils";

export const metadata = { title: "Jobs · Welyne HR" };
export const dynamic = "force-dynamic";

interface JobRollup {
  jobId: number;
  applicants: number;
  shortlisted: number;
}

export default async function JobsPage() {
  const apps = await apiGet<ApplicationSummary[]>("/applications", []);

  const byJob = new Map<number, JobRollup>();
  for (const a of apps) {
    const j = byJob.get(a.job_id) ?? { jobId: a.job_id, applicants: 0, shortlisted: 0 };
    j.applicants += 1;
    if (a.state === "SHORTLISTED") j.shortlisted += 1;
    byJob.set(a.job_id, j);
  }
  const jobs = [...byJob.values()].sort((a, b) => a.jobId - b.jobId);

  return (
    <>
      <PageHeader
        eyebrow="Jobs"
        title={`${jobs.length} ${jobs.length === 1 ? "job" : "jobs"}`}
        description="Derived from received applications. A dedicated jobs table (titles, departments, publication gate) lands in a later sprint."
      />

      {jobs.length === 0 ? (
        <div className="text-muted-foreground border border-dashed px-6 py-16 text-center text-sm">
          No jobs yet — they appear once applications are received.
        </div>
      ) : (
        <div className="grid gap-px border bg-border md:grid-cols-2 xl:grid-cols-3">
          {jobs.map((job) => (
            <article key={job.jobId} className="bg-card flex flex-col justify-between p-6">
              <div>
                <p className="eyebrow mb-4">Job</p>
                <h2 className="font-heading mb-1 text-lg font-semibold tracking-tight">
                  Job #{job.jobId}
                </h2>
              </div>
              <div className="mt-6 flex items-end gap-6 border-t pt-4">
                <div>
                  <p className="font-mono text-xl font-bold">{job.applicants}</p>
                  <p className="eyebrow">Applicants</p>
                </div>
                <div>
                  <p
                    className={cn(
                      "font-mono text-xl font-bold",
                      job.shortlisted > 0 && "text-primary",
                    )}
                  >
                    {job.shortlisted}
                  </p>
                  <p className="eyebrow">Shortlisted</p>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
