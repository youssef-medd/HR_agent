import { UploadCvDialog } from "@/components/applications/upload-cv-dialog";
import { PageHeader } from "@/components/shell/page-header";
import { StateBadge } from "@/components/shell/state-badge";
import { API_URL, type ApplicationSummary } from "@/lib/api/client";
import { getSessionToken } from "@/lib/api/server";
import { APPLICATION_STATES, type ApplicationState } from "@/lib/mocks/types";

export const metadata = { title: "Applications · Welyne HR" };
export const dynamic = "force-dynamic";

/** Pipeline order for the staged column view — terminal states last. */
const PIPELINE: ApplicationState[] = [
  "RECEIVED",
  "PARSED",
  "SCORED",
  "SHORTLISTED",
  "PRESCREENING",
  "PRESCREENED",
  "INTERVIEW_SCHEDULED",
  "INTERVIEWED",
  "OFFER",
  "DECLINE_PENDING",
  "POOL",
  "DECLINED",
];

async function fetchApplications(): Promise<ApplicationSummary[]> {
  const token = await getSessionToken();
  if (!token) return [];
  const res = await fetch(`${API_URL}/applications`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) return [];
  return (await res.json()) as ApplicationSummary[];
}

export default async function ApplicationsPage() {
  const apps = await fetchApplications();

  const byState = new Map<ApplicationState, ApplicationSummary[]>();
  for (const state of APPLICATION_STATES) byState.set(state, []);
  for (const app of apps) byState.get(app.state as ApplicationState)?.push(app);

  const stages = PIPELINE.filter((s) => (byState.get(s)?.length ?? 0) > 0);

  return (
    <>
      <PageHeader
        eyebrow="Applications"
        title="Pipeline"
        description="Each column is a state in the orchestrator's audited state machine. Illegal transitions are impossible by construction."
      >
        <UploadCvDialog />
      </PageHeader>

      {stages.length === 0 ? (
        <div className="text-muted-foreground border border-dashed px-6 py-16 text-center text-sm">
          No applications yet. Use <span className="text-foreground">Upload CV</span> to add one.
        </div>
      ) : (
        <div className="overflow-x-auto pb-4">
          <div className="flex min-w-max gap-px border bg-border">
            {stages.map((state) => {
              const stageApps = byState.get(state) ?? [];
              return (
                <div key={state} className="bg-background w-64 shrink-0">
                  <div className="bg-card flex items-center justify-between border-b px-4 py-3">
                    <StateBadge state={state} />
                    <span className="font-mono text-muted-foreground text-xs">
                      {stageApps.length}
                    </span>
                  </div>
                  <div className="space-y-px bg-border">
                    {stageApps.map((app) => (
                      <div key={app.id} className="bg-card p-4">
                        <p className="mb-0.5 text-sm font-medium">
                          {app.full_name || app.candidate_ref}
                        </p>
                        <p className="text-muted-foreground mb-2 text-xs">
                          Job #{app.job_id}
                        </p>
                        <p className="text-muted-foreground font-mono text-[10px]">
                          #{app.id} · {app.created_at.slice(0, 10)}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}
