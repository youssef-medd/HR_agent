import Link from "next/link";
import { ArrowUpRight, ChevronRight } from "lucide-react";

import { BrutalCounter, BrutalTile } from "@/components/dashboard/brutal-tile";
import {
  ApplicationsOverTime,
  PipelineByStage,
  type DayPoint,
  type StagePoint,
} from "@/components/dashboard/overview-charts";
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

/**
 * Local card title. `PageHeader` and the shared shell bits are used by the
 * other six console pages, so the brutalist treatment is kept here rather than
 * pushed into them until the rollout is approved.
 */
function CardTitle({ children, sub }: { children: React.ReactNode; sub?: string }) {
  return (
    <div className="mb-5">
      <h2 className="brutal-head text-lg">{children}</h2>
      {sub && (
        <p className="text-muted-foreground mt-2 text-[11px] font-bold tracking-widest uppercase">
          {sub}
        </p>
      )}
    </div>
  );
}

function ListHeader({
  title,
  count,
  href,
}: {
  title: string;
  count: number;
  href?: string;
}) {
  return (
    <div className="mb-4 flex items-center justify-between gap-3 border-b-[3px] border-black pb-2 dark:border-white">
      <div className="flex items-center gap-2.5">
        <h2 className="font-heading text-lg font-black tracking-tighter uppercase">
          {title}
        </h2>
        <span className="brutal-num flex h-6 min-w-6 items-center justify-center border-[2px] border-black px-1.5 text-xs dark:border-white">
          {count}
        </span>
      </div>
      {href && (
        <Link
          href={href}
          className="hover:text-primary inline-flex items-center gap-1 text-[11px] font-bold tracking-widest uppercase transition-colors"
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
    {
      label: "Active jobs",
      value: new Set(apps.map((a) => a.job_id)).size,
      hint: "open positions",
    },
    { label: "Applications", value: apps.length, hint: "total received" },
    {
      label: "In pipeline",
      value: apps.filter((a) => !TERMINAL.has(a.state)).length,
      hint: "in progress",
    },
  ];

  const recent = apps.slice(0, 6);

  return (
    <div className="relative">
      {/* Dot texture, behind everything */}
      <div
        aria-hidden
        className="brutal-dots pointer-events-none absolute inset-0 -z-10 opacity-[0.07]"
      />

      <header className="mb-8">
        <p className="text-primary text-[11px] font-black tracking-[0.2em] uppercase">
          Overview
        </p>
        <h1 className="font-heading mt-2 text-4xl font-black tracking-tighter uppercase md:text-5xl">
          Pipeline at a glance
        </h1>
        <p className="text-muted-foreground mt-3 max-w-xl text-xs font-bold tracking-widest uppercase">
          Live state of every application · human gates first
        </p>
      </header>

      {/* ---------- Stat row ---------- */}
      <div className="mb-6 grid grid-cols-2 gap-6 lg:grid-cols-4">
        {stats.map((s, i) => (
          <BrutalTile key={s.label} index={i}>
            <div className="brutal flex h-full flex-col gap-5 p-5">
              <p className="text-[10px] font-black tracking-[0.16em] uppercase opacity-60">
                {s.label}
              </p>
              <div className="mt-auto">
                <p className="brutal-num text-5xl leading-none">
                  <BrutalCounter value={s.value} />
                </p>
                <p className="mt-2 text-[10px] font-bold tracking-widest uppercase opacity-50">
                  {s.hint}
                </p>
              </div>
            </div>
          </BrutalTile>
        ))}

        {/* Accent tile — human gates awaiting review */}
        <BrutalTile index={3}>
          <Link href="/attention" className="group block h-full">
            <div className="brutal-accent flex h-full flex-col gap-5 p-5">
              <div className="flex items-start justify-between gap-2">
                <p className="text-[10px] font-black tracking-[0.16em] text-white uppercase">
                  Awaiting review
                </p>
                <ArrowUpRight
                  className="size-4 shrink-0 text-white transition-transform duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
                  aria-hidden
                />
              </div>
              <div className="mt-auto">
                <p className="brutal-num text-5xl leading-none text-white">
                  <BrutalCounter value={openAttention.length} />
                </p>
                <p className="mt-2 text-[10px] font-bold tracking-widest text-white/85 uppercase">
                  human gates open
                </p>
              </div>
            </div>
          </Link>
        </BrutalTile>
      </div>

      {/* ---------- Charts ---------- */}
      <div className="mb-6 grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <BrutalTile index={4} lift={false}>
          <section className="brutal h-full p-6">
            <CardTitle sub="Last 14 days">Applications received</CardTitle>
            <ApplicationsOverTime data={buildDaySeries(apps)} />
          </section>
        </BrutalTile>

        <BrutalTile index={5} lift={false}>
          <section className="brutal h-full p-6">
            <CardTitle sub="Current distribution">Pipeline by stage</CardTitle>
            {apps.length === 0 ? (
              <p className="text-muted-foreground py-10 text-center text-[11px] font-bold tracking-widest uppercase">
                No data yet
              </p>
            ) : (
              <PipelineByStage data={buildStageSeries(apps)} />
            )}
          </section>
        </BrutalTile>
      </div>

      {/* ---------- Queues ---------- */}
      <div className="grid gap-6 xl:grid-cols-[1.15fr_1fr]">
        <BrutalTile index={6} lift={false}>
          <section className="brutal h-full p-6">
            <ListHeader
              title="Needs attention"
              count={openAttention.length}
              href="/attention"
            />
            {openAttention.length === 0 ? (
              <div className="text-muted-foreground py-12 text-center text-[11px] font-bold tracking-widest uppercase">
                Nothing waiting on a human
              </div>
            ) : (
              <div className="space-y-2">
                {openAttention.map((item) => {
                  const name =
                    item.full_name ||
                    item.candidate_ref ||
                    `Application #${item.application_id}`;
                  return (
                    <Link
                      key={item.id}
                      href="/attention"
                      className="group hover:border-primary flex min-h-16 items-center gap-3 border-[2px] border-transparent px-3 transition-colors duration-150 hover:bg-black/[0.03] dark:hover:bg-white/[0.05]"
                    >
                      <Avatar label={name} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-bold">{name}</p>
                        <p className="brutal-num mt-0.5 text-[11px] opacity-50">
                          #{item.application_id}
                        </p>
                      </div>
                      <GatePill label={item.gate ?? item.reason.replaceAll("_", " ")} />
                      <ChevronRight
                        className="group-hover:text-primary size-4 shrink-0 opacity-40 transition-colors"
                        aria-hidden
                      />
                    </Link>
                  );
                })}
              </div>
            )}
          </section>
        </BrutalTile>

        <BrutalTile index={7} lift={false}>
          <section className="brutal h-full p-6">
            <ListHeader title="Recent activity" count={recent.length} />
            {recent.length === 0 ? (
              <div className="text-muted-foreground py-12 text-center text-[11px] font-bold tracking-widest uppercase">
                No applications yet
              </div>
            ) : (
              <div className="space-y-2">
                {recent.map((app) => {
                  const name = app.full_name || app.candidate_ref;
                  return (
                    <div
                      key={app.id}
                      className="flex min-h-16 items-center gap-3 border-[2px] border-transparent px-3"
                    >
                      <Avatar label={name} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-bold">{name}</p>
                        <p className="brutal-num mt-0.5 truncate text-[11px] opacity-50">
                          {app.job_title ?? `Job #${app.job_id}`}
                        </p>
                      </div>
                      <StateBadge state={app.state as ApplicationState} />
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </BrutalTile>
      </div>
    </div>
  );
}
