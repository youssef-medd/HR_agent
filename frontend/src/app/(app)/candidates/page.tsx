import { PageHeader } from "@/components/shell/page-header";
import { StateBadge } from "@/components/shell/state-badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { type ApplicationSummary } from "@/lib/api/client";
import { apiGet } from "@/lib/api/server";
import { type ApplicationState } from "@/lib/mocks/types";

export const metadata = { title: "Candidates · Welyne HR" };
export const dynamic = "force-dynamic";

const REC_STYLE: Record<string, string> = {
  shortlist: "bg-orange-50 text-primary dark:bg-orange-500/15",
  pool: "bg-slate-100 text-slate-600 dark:bg-slate-500/15 dark:text-slate-400",
  decline: "bg-red-50 text-red-600 dark:bg-red-500/15 dark:text-red-400",
};

function ScoreCell({
  score,
  recommendation,
}: {
  score: number | null;
  recommendation: string | null;
}) {
  if (score === null || score === undefined) {
    return <span className="text-muted-foreground font-mono text-xs">—</span>;
  }
  return (
    <span className="flex items-center gap-2">
      <span className="bg-muted relative h-1.5 w-14 overflow-hidden rounded-full">
        <span
          className={`absolute inset-y-0 left-0 rounded-full ${score >= 70 ? "bg-primary" : "bg-muted-foreground/50"}`}
          style={{ width: `${score}%` }}
        />
      </span>
      <span className="font-mono text-xs font-semibold">{score}</span>
      {recommendation && (
        <span className={`chip capitalize ${REC_STYLE[recommendation] ?? "bg-muted text-muted-foreground"}`}>
          {recommendation}
        </span>
      )}
    </span>
  );
}

export default async function CandidatesPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const all = await apiGet<ApplicationSummary[]>("/applications", []);
  const needle = (q ?? "").trim().toLowerCase();
  const apps = needle
    ? all.filter(
        (a) =>
          (a.full_name ?? "").toLowerCase().includes(needle) ||
          a.candidate_ref.toLowerCase().includes(needle),
      )
    : all;
  const sorted = [...apps].sort((a, b) => (b.score ?? -1) - (a.score ?? -1));

  return (
    <>
      <PageHeader
        eyebrow="Candidates"
        title={
          needle
            ? `${apps.length} match${apps.length === 1 ? "" : "es"} for “${q}”`
            : `${apps.length} ${apps.length === 1 ? "candidate" : "candidates"}`
        }
        description="Scores come from the masked judge model (A4) — identity attributes are never visible to it."
      />

      {apps.length === 0 ? (
        <div className="surface text-muted-foreground px-6 py-16 text-center text-sm">
          No candidates yet. Upload a CV from the Applications page.
        </div>
      ) : (
        <div className="surface overflow-x-auto p-2">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="eyebrow h-11">Candidate</TableHead>
                <TableHead className="eyebrow h-11">Applied for</TableHead>
                <TableHead className="eyebrow h-11">Score</TableHead>
                <TableHead className="eyebrow h-11">Stage</TableHead>
                <TableHead className="eyebrow h-11 text-right">Applied</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>
                    <p className="font-medium">{c.full_name || c.candidate_ref}</p>
                    <p className="text-muted-foreground text-xs">#{c.id}</p>
                  </TableCell>
                  <TableCell className="text-sm">Job #{c.job_id}</TableCell>
                  <TableCell>
                    <ScoreCell score={c.score} recommendation={c.recommendation} />
                  </TableCell>
                  <TableCell>
                    <StateBadge state={c.state as ApplicationState} />
                  </TableCell>
                  <TableCell className="text-muted-foreground text-right font-mono text-xs">
                    {c.created_at.slice(0, 10)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  );
}
