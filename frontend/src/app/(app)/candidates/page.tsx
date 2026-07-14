import { CandidatesTable } from "@/components/candidates/candidates-table";
import { PageHeader } from "@/components/shell/page-header";
import { type ApplicationSummary } from "@/lib/api/client";
import { apiGet } from "@/lib/api/server";

export const metadata = { title: "Candidates · Welyne HR" };
export const dynamic = "force-dynamic";

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
        <CandidatesTable rows={apps} />
      )}
    </>
  );
}
