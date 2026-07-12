import { UploadCvDialog } from "@/components/applications/upload-cv-dialog";
import { PageHeader } from "@/components/shell/page-header";
import { StateBadge } from "@/components/shell/state-badge";
import { mockApplications } from "@/lib/mocks/data";
import { APPLICATION_STATES, type ApplicationState } from "@/lib/mocks/types";

export const metadata = { title: "Applications · Welyne HR" };

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

export default function ApplicationsPage() {
  const byState = new Map<ApplicationState, typeof mockApplications>();
  for (const state of APPLICATION_STATES) byState.set(state, []);
  for (const app of mockApplications) byState.get(app.state)?.push(app);

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

      <div className="overflow-x-auto pb-4">
        <div className="flex min-w-max gap-px border bg-border">
          {stages.map((state) => {
            const apps = byState.get(state) ?? [];
            return (
              <div key={state} className="bg-background w-64 shrink-0">
                <div className="bg-card flex items-center justify-between border-b px-4 py-3">
                  <StateBadge state={state} />
                  <span className="font-mono text-muted-foreground text-xs">
                    {apps.length}
                  </span>
                </div>
                <div className="space-y-px bg-border">
                  {apps.map((app) => (
                    <div key={app.id} className="bg-card p-4">
                      <p className="mb-0.5 text-sm font-medium">
                        {app.candidateName}
                      </p>
                      <p className="text-muted-foreground mb-2 text-xs">
                        {app.jobTitle}
                      </p>
                      <p className="text-muted-foreground font-mono text-[10px]">
                        #{app.id} · {app.updatedAt}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
