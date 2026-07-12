import Link from "next/link";
import { ArrowUpRight } from "lucide-react";

import { PageHeader } from "@/components/shell/page-header";
import { StateBadge } from "@/components/shell/state-badge";
import { type ApplicationSummary, type AttentionItem } from "@/lib/api/client";
import { apiGet } from "@/lib/api/server";
import { type ApplicationState } from "@/lib/mocks/types";

export const metadata = { title: "Overview · Welyne HR" };
export const dynamic = "force-dynamic";

const TERMINAL: ReadonlySet<string> = new Set([
  "POOL",
  "ONBOARDING",
  "DECLINED",
  "NEEDS_ATTENTION",
]);

export default async function OverviewPage() {
  const [apps, attention] = await Promise.all([
    apiGet<ApplicationSummary[]>("/applications", []),
    apiGet<AttentionItem[]>("/needs-attention", []),
  ]);

  const openAttention = attention.filter((a) => a.status === "open");
  const stats = [
    { label: "Active jobs", value: new Set(apps.map((a) => a.job_id)).size },
    { label: "Applications", value: apps.length },
    { label: "In pipeline", value: apps.filter((a) => !TERMINAL.has(a.state)).length },
    { label: "Awaiting review", value: openAttention.length, accent: true },
  ];

  const recent = apps.slice(0, 6);

  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="Pipeline at a glance"
        description="Live state of every application, with human gates surfaced first."
      />

      {/* Stat row */}
      <div className="mb-10 grid grid-cols-2 gap-px border bg-border lg:grid-cols-4">
        {stats.map((s) => (
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
          {openAttention.length === 0 ? (
            <div className="text-muted-foreground border border-dashed px-6 py-10 text-center text-xs">
              Nothing waiting on a human.
            </div>
          ) : (
            <div className="space-y-px border bg-border">
              {openAttention.map((item) => (
                <Link
                  key={item.id}
                  href="/attention"
                  className="bg-card hover:bg-accent block p-4 transition-colors duration-200"
                >
                  <div className="mb-1.5 flex items-center justify-between gap-4">
                    <span className="text-sm font-medium">
                      {item.full_name || item.candidate_ref || `Application #${item.application_id}`}
                    </span>
                    <span className="font-mono text-destructive text-[10px] tracking-[0.08em] uppercase">
                      {item.gate ?? item.reason.replaceAll("_", " ")}
                    </span>
                  </div>
                  <p className="text-muted-foreground line-clamp-2 text-xs leading-relaxed">
                    app #{item.application_id}
                  </p>
                </Link>
              ))}
            </div>
          )}
        </section>

        {/* Recent activity */}
        <section>
          <p className="eyebrow mb-4">Recent activity</p>
          {recent.length === 0 ? (
            <div className="text-muted-foreground border border-dashed px-6 py-10 text-center text-xs">
              No applications yet.
            </div>
          ) : (
            <div className="space-y-px border bg-border">
              {recent.map((app) => (
                <div
                  key={app.id}
                  className="bg-card flex items-center justify-between gap-4 p-4"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {app.full_name || app.candidate_ref}
                    </p>
                    <p className="text-muted-foreground truncate text-xs">Job #{app.job_id}</p>
                  </div>
                  <StateBadge state={app.state as ApplicationState} />
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </>
  );
}
