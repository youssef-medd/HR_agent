import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { PageHeader } from "@/components/shell/page-header";
import { StateBadge } from "@/components/shell/state-badge";
import {
  mockApplications,
  mockAttention,
  mockStats,
} from "@/lib/mocks/data";

export const metadata = { title: "Overview · Welyne HR" };

const STATS = [
  { label: "Active jobs", value: mockStats.activeJobs },
  { label: "Applications", value: mockStats.totalApplications },
  { label: "In pipeline", value: mockStats.inPipeline },
  { label: "Awaiting review", value: mockStats.awaitingReview, accent: true },
];

export default function OverviewPage() {
  const openAttention = mockAttention.filter((a) => a.status === "open");
  const recent = [...mockApplications]
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    .slice(0, 6);

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Pipeline at a glance"
        description="Live state of every application, with human gates surfaced first."
      />

      {/* Stat row */}
      <div className="mb-10 grid grid-cols-2 gap-px border bg-border lg:grid-cols-4">
        {STATS.map((s) => (
          <div key={s.label} className="bg-card p-5">
            <p className="eyebrow mb-3">{s.label}</p>
            <p
              className={`font-mono text-3xl font-bold tracking-tight ${
                s.accent && s.value > 0 ? "text-primary" : ""
              }`}
            >
              {s.value}
            </p>
          </div>
        ))}
      </div>

      <div className="grid gap-10 xl:grid-cols-[1.2fr_1fr]">
        {/* Needs attention queue */}
        <section>
          <div className="mb-4 flex items-center justify-between">
            <p className="eyebrow eyebrow-accent">Needs attention</p>
            <Link
              href="/attention"
              className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs transition-colors duration-200"
            >
              View all <ArrowUpRight className="size-3" aria-hidden />
            </Link>
          </div>
          <div className="space-y-px border bg-border">
            {openAttention.map((item) => (
              <Link
                key={item.id}
                href="/attention"
                className="bg-card hover:bg-accent block p-4 transition-colors duration-200"
              >
                <div className="mb-1.5 flex items-center justify-between gap-4">
                  <span className="text-sm font-medium">
                    {item.candidateName}
                    <span className="text-muted-foreground">
                      {" "}
                      · {item.jobTitle}
                    </span>
                  </span>
                  <span className="font-mono text-destructive text-[10px] tracking-[0.08em] uppercase">
                    {item.gate ?? item.reason.replaceAll("_", " ")}
                  </span>
                </div>
                <p className="text-muted-foreground line-clamp-2 text-xs leading-relaxed">
                  {item.context}
                </p>
              </Link>
            ))}
          </div>
        </section>

        {/* Recent activity */}
        <section>
          <p className="eyebrow mb-4">Recent activity</p>
          <div className="space-y-px border bg-border">
            {recent.map((app) => (
              <div
                key={app.id}
                className="bg-card flex items-center justify-between gap-4 p-4"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {app.candidateName}
                  </p>
                  <p className="text-muted-foreground truncate text-xs">
                    {app.jobTitle}
                  </p>
                </div>
                <StateBadge state={app.state} />
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}
