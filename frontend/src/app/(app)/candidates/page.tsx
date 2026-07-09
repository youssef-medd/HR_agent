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
import { mockCandidates } from "@/lib/mocks/data";

export const metadata = { title: "Candidates · Welyne HR" };

function ScoreCell({ score }: { score: number | null }) {
  if (score === null) {
    return <span className="text-muted-foreground font-mono text-xs">—</span>;
  }
  return (
    <span className="flex items-center gap-2">
      <span className="bg-muted relative h-1 w-14 overflow-hidden">
        <span
          className={`absolute inset-y-0 left-0 ${
            score >= 75 ? "bg-primary" : "bg-muted-foreground"
          }`}
          style={{ width: `${score}%` }}
        />
      </span>
      <span className="font-mono text-xs">{score}</span>
    </span>
  );
}

export default function CandidatesPage() {
  const sorted = [...mockCandidates].sort(
    (a, b) => (b.score ?? -1) - (a.score ?? -1)
  );

  return (
    <>
      <PageHeader
        eyebrow="Candidates"
        title={`${mockCandidates.length} candidates`}
        description="Scores are produced by the masked judge model — identity attributes are never visible to it."
      />

      <div className="overflow-x-auto border">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="eyebrow h-11">Candidate</TableHead>
              <TableHead className="eyebrow h-11">Applied for</TableHead>
              <TableHead className="eyebrow h-11">Score</TableHead>
              <TableHead className="eyebrow h-11">Stage</TableHead>
              <TableHead className="eyebrow h-11">Source</TableHead>
              <TableHead className="eyebrow h-11 text-right">Applied</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((c) => (
              <TableRow key={c.ref}>
                <TableCell>
                  <p className="font-medium">{c.fullName}</p>
                  <p className="text-muted-foreground text-xs">{c.location}</p>
                </TableCell>
                <TableCell className="text-sm">{c.jobTitle}</TableCell>
                <TableCell>
                  <ScoreCell score={c.score} />
                </TableCell>
                <TableCell>
                  <StateBadge state={c.state} />
                </TableCell>
                <TableCell className="text-muted-foreground text-sm">
                  {c.source}
                </TableCell>
                <TableCell className="text-muted-foreground text-right font-mono text-xs">
                  {c.appliedAt}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  );
}
