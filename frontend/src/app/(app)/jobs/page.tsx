import { CreateJobDialog } from "@/components/jobs/create-job-dialog";
import { PageHeader } from "@/components/shell/page-header";
import { type JobView } from "@/lib/api/client";
import { apiGet } from "@/lib/api/server";
import { cn } from "@/lib/utils";

export const metadata = { title: "Jobs · Welyne HR" };
export const dynamic = "force-dynamic";

const STATUS_STYLE: Record<string, string> = {
  published: "bg-orange-50 text-primary dark:bg-orange-500/15",
  draft: "bg-muted text-muted-foreground",
  closed: "bg-muted text-muted-foreground line-through",
};

export default async function JobsPage() {
  const jobs = await apiGet<JobView[]>("/jobs", []);

  return (
    <>
      <PageHeader
        eyebrow="Jobs"
        title={`${jobs.length} job ${jobs.length === 1 ? "posting" : "postings"}`}
        description="Each posting's description is the rubric the judge scores candidates against."
      >
        <CreateJobDialog />
      </PageHeader>

      {jobs.length === 0 ? (
        <div className="surface text-muted-foreground px-6 py-16 text-center text-sm">
          No jobs yet. Create one, then upload CVs against it.
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {jobs.map((job) => (
            <article
              key={job.id}
              className="surface flex flex-col justify-between p-6"
            >
              <div>
                <div className="mb-4 flex items-start justify-between gap-3">
                  <p className="eyebrow">{job.department ?? `Job #${job.id}`}</p>
                  <span
                    className={cn(
                      "chip capitalize",
                      STATUS_STYLE[job.status] ?? "bg-muted text-muted-foreground",
                    )}
                  >
                    {job.status}
                  </span>
                </div>
                <h2 className="font-heading mb-1 text-lg font-semibold tracking-tight">
                  {job.title}
                </h2>
                <p className="text-muted-foreground text-sm">
                  {job.location ?? "—"}
                </p>
                {job.description && (
                  <p className="text-muted-foreground mt-3 line-clamp-3 text-xs leading-relaxed">
                    {job.description}
                  </p>
                )}
              </div>

              <div className="mt-6 flex items-end justify-between border-t pt-4">
                <div className="flex gap-6">
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
                <p className="text-muted-foreground font-mono text-xs">
                  {job.created_at.slice(0, 10)}
                </p>
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
