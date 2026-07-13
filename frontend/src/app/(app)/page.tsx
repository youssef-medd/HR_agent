import Link from "next/link";
import { ArrowUpRight, ChevronRight } from "lucide-react";

import {
  ApplicationsOverTime,
  PipelineByStage,
  type DayPoint,
  type StagePoint,
} from "@/components/dashboard/overview-charts";
import { PageHeader } from "@/components/shell/page-header";
import { Avatar, GatePill } from "@/components/shell/row-bits";
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

const STAGE_ORDER = [
  "RECEIVED",
  "PARSED",
  "SCORED",
  "SHORTLISTED",
  "POOL",
  "DECLINE_PENDING",
  "DECLINED",
  "NEEDS_ATTENTION",
];

function titleCase(s: string): string {
  const words = s.replaceAll("_", " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Applications per day, last 14 days, empty days filled with zero. */
function buildDaySeries(apps: ApplicationSummary[]): DayPoint[] {
  const fmt = new Intl.DateTimeFormat("en-GB", { month: "short", day: "2-digit" });
  const counts = new Map<string, number>();
  for (const a of apps) {
    const key = a.created_at.slice(0, 10);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const out: DayPoint[] = [];
  const today = new Date();
  for (let i = 13; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    out.push({ day: fmt.format(d), count: counts.get(key) ?? 0 });
  }
  return out;
}

function buildStageSeries(apps: ApplicationSummary[]): StagePoint[] {
  const counts = new Map<string, number>();
  for (const a of apps) counts.set(a.state, (counts.get(a.state) ?? 0) + 1);
  return STAGE_ORDER.filter((s) => (counts.get(s) ?? 0) > 0).map((s) => ({
    stage: titleCase(s),
    count: counts.get(s) ?? 0,
  }));
}

function SectionHeader({
  title,
  count,
  href,
}: {
  title: string;
  count: number;
  href?: string;
}) {
  return (
    <div className="flex items-center justify-between px-6 pt-5 pb-3">
      <div className="flex items-center gap-2">
        <h2 className="font-heading text-base font-semibold tracking-tight">{title}</h2>
        <span className="bg-muted text-muted-foreground font-mono flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[10px]">
          {count}
        </span>
      </div>
      {href && (
        <Link
          href={href}
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs transition-colors duration-200"
        >
          View all <ArrowUpRight className="size-3" aria-hidden />
        </Link>
      )}
    </div>
  );
}

export default async function OverviewPage() {
  const [apps, attention] = await Promise.all([
    apiGet<ApplicationSummary[]>("/applications", []),
    apiGet<AttentionItem[]>("/needs-attention", []),
  ]);

  const openAttention = attention.filter((a) => a.status === "open");
  const stats = [
    { label: "Active jobs", value: new Set(apps.map((a) => a.job_id)).size, hint: "open positions" },
    { label: "Applications", value: apps.length, hint: "total received" },
    {
      label: "In pipeline",
      value: apps.filter((a) => !TERMINAL.has(a.state)).length,
      hint: "in progress",
    },
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
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="surface flex flex-col gap-5 p-6">
            <p className="eyebrow">{s.label}</p>
            <div className="mt-auto">
              <p className="font-mono text-4xl leading-none font-bold tracking-tight tabular-nums">
                {s.value}
              </p>
              <p className="text-muted-foreground mt-2 text-xs">{s.hint}</p>
            </div>
          </div>
        ))}

        {/* Accent tile — human gates awaiting review */}
        <Link href="/attention" className="surface-accent group flex flex-col gap-5 p-6">
          <div className="flex items-center justify-between">
            <p className="font-mono text-[11px] font-medium tracking-[0.16em] text-white/80 uppercase">
              Awaiting review
            </p>
            <ArrowUpRight
              className="size-4 text-white/70 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
              aria-hidden
            />
          </div>
          <div className="mt-auto">
            <p className="font-mono text-4xl leading-none font-bold tracking-tight tabular-nums">
              {openAttention.length}
            </p>
            <p className="mt-2 text-xs text-white/80">human gates open</p>
          </div>
        </Link>
      </div>

      {/* Charts */}
      <div className="mb-6 grid gap-4 xl:grid-cols-[1.4fr_1fr]">
        <section className="surface p-6">
          <div className="mb-4">
            <h2 className="font-heading text-base font-semibold tracking-tight">
              Applications received
            </h2>
            <p className="text-muted-foreground text-xs">Last 14 days</p>
          </div>
          <ApplicationsOverTime data={buildDaySeries(apps)} />
        </section>
        <section className="surface p-6">
          <div className="mb-4">
            <h2 className="font-heading text-base font-semibold tracking-tight">
              Pipeline by stage
            </h2>
            <p className="text-muted-foreground text-xs">Current distribution</p>
          </div>
          {apps.length === 0 ? (
            <p className="text-muted-foreground py-10 text-center text-xs">No data yet.</p>
          ) : (
            <PipelineByStage data={buildStageSeries(apps)} />
          )}
        </section>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.15fr_1fr]">
        {/* Needs attention queue */}
        <section className="surface pb-3">
          <SectionHeader title="Needs attention" count={openAttention.length} href="/attention" />
          {openAttention.length === 0 ? (
            <div className="text-muted-foreground px-6 py-12 text-center text-xs">
              Nothing waiting on a human.
            </div>
          ) : (
            <div className="space-y-1.5 px-3 pb-2">
              {openAttention.map((item) => {
                const name =
                  item.full_name || item.candidate_ref || `Application #${item.application_id}`;
                return (
                  <Link
                    key={item.id}
                    href="/attention"
                    className="group hover:bg-accent flex min-h-16 items-center gap-3 rounded-2xl px-3 transition-colors duration-200"
                  >
                    <Avatar label={name} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{name}</p>
                      <p className="text-muted-foreground font-mono mt-0.5 text-[11px]">
                        app #{item.application_id}
                      </p>
                    </div>
                    <GatePill label={item.gate ?? item.reason.replaceAll("_", " ")} />
                    <ChevronRight
                      className="text-muted-foreground group-hover:text-foreground size-4 shrink-0 transition-colors duration-200"
                      aria-hidden
                    />
                  </Link>
                );
              })}
            </div>
          )}
        </section>

        {/* Recent activity */}
        <section className="surface pb-3">
          <SectionHeader title="Recent activity" count={recent.length} />
          {recent.length === 0 ? (
            <div className="text-muted-foreground px-6 py-12 text-center text-xs">
              No applications yet.
            </div>
          ) : (
            <div className="space-y-1.5 px-3 pb-2">
              {recent.map((app) => {
                const name = app.full_name || app.candidate_ref;
                return (
                  <div
                    key={app.id}
                    className="flex min-h-16 items-center gap-3 rounded-2xl px-3"
                  >
                    <Avatar label={name} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{name}</p>
                      <p className="text-muted-foreground font-mono mt-0.5 text-[11px]">
                        Job #{app.job_id}
                      </p>
                    </div>
                    <StateBadge state={app.state as ApplicationState} />
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </>
  );
}
