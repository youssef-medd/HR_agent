import { PageHeader } from "@/components/shell/page-header";
import { mockJobs } from "@/lib/mocks/data";
import { cn } from "@/lib/utils";

export const metadata = { title: "Jobs · Welyne HR" };

const STATUS_STYLE: Record<string, string> = {
  published: "text-primary border-primary/40",
  draft: "text-muted-foreground border-border",
  closed: "text-muted-foreground border-border line-through",
};

export default function JobsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Jobs"
        title={`${mockJobs.length} job postings`}
        description="External publication passes through a human gate before anything goes live."
      />

      <div className="grid gap-px border bg-border md:grid-cols-2 xl:grid-cols-3">
        {mockJobs.map((job) => (
          <article
            key={job.id}
            className="bg-card hover:bg-accent flex flex-col justify-between p-6 transition-colors duration-200"
          >
            <div>
              <div className="mb-4 flex items-start justify-between gap-3">
                <p className="eyebrow">{job.department}</p>
                <span
                  className={cn(
                    "font-mono border px-2 py-0.5 text-[10px] tracking-[0.08em] uppercase",
                    STATUS_STYLE[job.status]
                  )}
                >
                  {job.status}
                </span>
              </div>
              <h2 className="font-heading mb-1 text-lg font-semibold tracking-tight">
                {job.title}
              </h2>
              <p className="text-muted-foreground text-sm">{job.location}</p>
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
                      job.shortlisted > 0 && "text-primary"
                    )}
                  >
                    {job.shortlisted}
                  </p>
                  <p className="eyebrow">Shortlisted</p>
                </div>
              </div>
              <p className="text-muted-foreground font-mono text-xs">
                {job.publishedAt ?? "not published"}
              </p>
            </div>
          </article>
        ))}
      </div>
    </>
  );
}
