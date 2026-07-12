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

export default async function CandidatesPage() {
  const apps = await apiGet<ApplicationSummary[]>("/applications", []);

  return (
    <>
      <PageHeader
        eyebrow="Candidates"
        title={`${apps.length} ${apps.length === 1 ? "candidate" : "candidates"}`}
        description="Scores are produced by the masked judge model (A4) — not yet wired, so the score column is empty until scoring lands."
      />

      {apps.length === 0 ? (
        <div className="text-muted-foreground border border-dashed px-6 py-16 text-center text-sm">
          No candidates yet. Upload a CV from the Applications page.
        </div>
      ) : (
        <div className="overflow-x-auto border">
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
              {apps.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>
                    <p className="font-medium">{c.full_name || c.candidate_ref}</p>
                    <p className="text-muted-foreground text-xs">#{c.id}</p>
                  </TableCell>
                  <TableCell className="text-sm">Job #{c.job_id}</TableCell>
                  <TableCell>
                    <span className="text-muted-foreground font-mono text-xs">—</span>
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
