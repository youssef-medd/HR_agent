import { ExportButtons } from "@/components/reports/export-buttons";
import { PageHeader } from "@/components/shell/page-header";
import { type ReportOverview } from "@/lib/api/client";
import { apiGet } from "@/lib/api/server";

export const metadata = { title: "Reports · Welyne HR" };
export const dynamic = "force-dynamic";

const EMPTY: ReportOverview = {
  total_applications: 0,
  by_state: {},
  by_source: {},
  source_conversion: {},
  funnel: [],
  avg_score: null,
  score_distribution: {},
  shortlist_rate: 0,
  hire_rate: 0,
  open_gates: 0,
  per_job: [],
};

function titleCase(s: string): string {
  const words = s.replaceAll("_", " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function pct(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

function hours(h: number | null): string {
  if (h === null) return "—";
  if (h < 1) return `${Math.round(h * 60)}m`;
  if (h < 48) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
}

export default async function ReportsPage() {
  const data = await apiGet<ReportOverview>("/reports/overview", EMPTY);
  const total = data.total_applications;

  const stats = [
    { label: "Applications", value: String(total), hint: "total received" },
    { label: "Avg score", value: data.avg_score === null ? "—" : String(data.avg_score), hint: "judged /100" },
    { label: "Shortlist rate", value: pct(data.shortlist_rate), hint: "of all applicants" },
    { label: "Hire rate", value: pct(data.hire_rate), hint: "of all applicants" },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Reports"
        title="Recruitment analytics"
        description="Funnel conversion, time-in-stage and per-job outcomes across every application."
      >
        <ExportButtons />
      </PageHeader>

      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="surface flex flex-col gap-5 p-6">
            <p className="eyebrow">{s.label}</p>
            <div className="mt-auto">
              <p className="text-4xl leading-none font-bold tracking-tight tabular-nums">
                {s.value}
              </p>
              <p className="text-muted-foreground mt-2 text-xs">{s.hint}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="mb-6 grid gap-6 lg:grid-cols-2">
        {Object.keys(data.source_conversion).length > 0 && (
          <div className="surface p-6">
            <h2 className="font-heading mb-3 text-base font-semibold tracking-tight">
              Source efficiency
            </h2>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-muted-foreground text-left text-xs">
                  <th className="pb-2 font-medium">Source</th>
                  <th className="pb-2 text-right font-medium">Applied</th>
                  <th className="pb-2 text-right font-medium">Shortlist</th>
                  <th className="pb-2 text-right font-medium">Hire</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.source_conversion)
                  .sort((a, b) => b[1].applied - a[1].applied)
                  .map(([src, c]) => (
                    <tr key={src} className="border-t">
                      <td className="py-1.5">{titleCase(src)}</td>
                      <td className="py-1.5 text-right tabular-nums">{c.applied}</td>
                      <td className="py-1.5 text-right tabular-nums">{pct(c.shortlist_rate)}</td>
                      <td className="py-1.5 text-right tabular-nums">{pct(c.hire_rate)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}

        {Object.values(data.score_distribution).some((n) => n > 0) && (
          <div className="surface p-6">
            <h2 className="font-heading mb-3 text-base font-semibold tracking-tight">
              Score distribution
            </h2>
            <div className="space-y-2">
              {Object.entries(data.score_distribution).map(([band, n]) => {
                const max = Math.max(1, ...Object.values(data.score_distribution));
                return (
                  <div key={band} className="grid grid-cols-[4rem_1fr_2rem] items-center gap-3">
                    <span className="text-muted-foreground text-xs">{band}</span>
                    <div className="bg-muted h-2.5 overflow-hidden rounded-full">
                      <div
                        className={`h-full rounded-full ${band.startsWith("70") || band.startsWith("85") ? "bg-primary" : "bg-muted-foreground/50"}`}
                        style={{ width: `${(n / max) * 100}%` }}
                      />
                    </div>
                    <span className="text-right text-xs tabular-nums">{n}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
        {/* Funnel */}
        <section className="surface p-6">
          <div className="mb-5">
            <h2 className="font-heading text-base font-semibold tracking-tight">Conversion funnel</h2>
            <p className="text-muted-foreground text-xs">
              Reach per stage · conversion from the previous stage · avg time from received
            </p>
          </div>

          {total === 0 ? (
            <p className="text-muted-foreground py-10 text-center text-xs">No data yet.</p>
          ) : (
            <div className="space-y-3">
              {data.funnel.map((f) => {
                const width = total > 0 ? Math.max(2, (f.reached / total) * 100) : 0;
                return (
                  <div key={f.stage}>
                    <div className="mb-1 flex items-baseline justify-between text-sm">
                      <span className="font-medium">{titleCase(f.stage)}</span>
                      <span className="text-muted-foreground tabular-nums text-xs">
                        {f.reached} · {pct(f.rate_from_prev)} · {hours(f.avg_hours_from_received)}
                      </span>
                    </div>
                    <div className="bg-muted h-2.5 overflow-hidden rounded-full">
                      <div
                        className="bg-primary h-full rounded-full"
                        style={{ width: `${width}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Per-job */}
        <section className="surface p-6">
          <div className="mb-5">
            <h2 className="font-heading text-base font-semibold tracking-tight">By job</h2>
            <p className="text-muted-foreground text-xs">Applicants and shortlist reach per role</p>
          </div>

          {data.per_job.length === 0 ? (
            <p className="text-muted-foreground py-10 text-center text-xs">No jobs yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted-foreground border-b text-left text-xs">
                    <th className="pb-2 font-medium">Job</th>
                    <th className="pb-2 text-right font-medium">Applicants</th>
                    <th className="pb-2 text-right font-medium">Shortlisted</th>
                  </tr>
                </thead>
                <tbody>
                  {data.per_job.map((j) => (
                    <tr key={j.job_id} className="border-b last:border-0">
                      <td className="py-2.5">
                        <span className="text-muted-foreground mr-1 text-xs">#{j.job_id}</span>
                        {j.title}
                      </td>
                      <td className="py-2.5 text-right tabular-nums">{j.applicants}</td>
                      <td className="py-2.5 text-right tabular-nums">{j.shortlisted}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
