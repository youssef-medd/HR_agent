"use client";

/**
 * Candidates table — resizable columns, sort menu, CSV/JSON export, row
 * selection and pagination, staggered row entrance. Runs on the real
 * ApplicationSummary rows; visual language follows the console (surface card,
 * soft chips, brand orange).
 */

import * as React from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  ArrowDownUp,
  Briefcase,
  CalendarDays,
  ChevronDown,
  Download,
  Gauge,
  Layers,
  UserRound,
} from "lucide-react";
import { StateBadge } from "@/components/shell/state-badge";
import type { ApplicationSummary } from "@/lib/api/client";
import { type ApplicationState } from "@/lib/mocks/types";

const REC_STYLE: Record<string, string> = {
  shortlist: "bg-orange-50 text-primary dark:bg-orange-500/15",
  pool: "bg-slate-100 text-slate-600 dark:bg-slate-500/15 dark:text-slate-400",
  decline: "bg-red-50 text-red-600 dark:bg-red-500/15 dark:text-red-400",
};

type SortField = "name" | "job" | "score" | "state" | "applied";
type SortOrder = "asc" | "desc";

const SORT_LABELS: Record<SortField, string> = {
  name: "Name",
  job: "Job",
  score: "Score",
  state: "Stage",
  applied: "Applied",
};

const PAGE_SIZE = 10;

function ScoreCell({
  score,
  recommendation,
}: {
  score: number | null;
  recommendation: string | null;
}) {
  if (score === null || score === undefined) {
    return <span className="text-muted-foreground text-xs">—</span>;
  }
  return (
    <span className="flex items-center gap-2">
      <span className="bg-muted relative h-1.5 w-14 shrink-0 overflow-hidden rounded-full">
        <span
          className={`absolute inset-y-0 left-0 rounded-full ${score >= 70 ? "bg-primary" : "bg-muted-foreground/50"}`}
          style={{ width: `${score}%` }}
        />
      </span>
      <span className="text-xs font-semibold">{score}</span>
      {recommendation && (
        <span
          className={`chip capitalize ${REC_STYLE[recommendation] ?? "bg-muted text-muted-foreground"}`}
        >
          {recommendation}
        </span>
      )}
    </span>
  );
}

function MenuButton({
  open,
  onToggle,
  icon,
  label,
  badge,
  children,
}: {
  open: boolean;
  onToggle: () => void;
  icon: React.ReactNode;
  label: string;
  badge?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="relative">
      <button
        onClick={onToggle}
        className="bg-card hover:bg-accent text-foreground flex items-center gap-2 rounded-full border px-3.5 py-2 text-sm transition-colors duration-200"
      >
        {icon}
        {label}
        {badge && (
          <span className="bg-primary rounded-full px-1.5 py-0.5 text-[10px] font-semibold text-white">
            {badge}
          </span>
        )}
        <ChevronDown className="size-3.5 opacity-50" aria-hidden />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={onToggle} />
          <div className="bg-popover absolute right-0 z-20 mt-1.5 w-44 overflow-hidden rounded-2xl border py-1 shadow-lg">
            {children}
          </div>
        </>
      )}
    </div>
  );
}

export function CandidatesTable({ rows }: { rows: ApplicationSummary[] }) {
  const reduced = useReducedMotion();
  const [selected, setSelected] = React.useState<Set<number>>(new Set());
  const [page, setPage] = React.useState(1);
  const [sortField, setSortField] = React.useState<SortField | null>("score");
  const [sortOrder, setSortOrder] = React.useState<SortOrder>("desc");
  const [sortOpen, setSortOpen] = React.useState(false);
  const [exportOpen, setExportOpen] = React.useState(false);

  const widths: Record<string, number> = {
    check: 44,
    candidate: 220,
    job: 110,
    score: 210,
    stage: 160,
    applied: 110,
  };

  function toggleSort(field: SortField) {
    if (sortField === field) {
      setSortOrder((o) => (o === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortOrder(field === "score" || field === "applied" ? "desc" : "asc");
    }
    setSortOpen(false);
    setPage(1);
  }

  const sorted = React.useMemo(() => {
    if (!sortField) return rows;
    const val = (r: ApplicationSummary): string | number => {
      switch (sortField) {
        case "name":
          return (r.full_name || r.candidate_ref).toLowerCase();
        case "job":
          return r.job_id;
        case "score":
          return r.score ?? -1;
        case "state":
          return r.state;
        case "applied":
          return r.created_at;
      }
    };
    return [...rows].sort((a, b) => {
      const av = val(a);
      const bv = val(b);
      if (av < bv) return sortOrder === "asc" ? -1 : 1;
      if (av > bv) return sortOrder === "asc" ? 1 : -1;
      return 0;
    });
  }, [rows, sortField, sortOrder]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const pageRows = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  function toggleRow(id: number) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setSelected((s) =>
      s.size === pageRows.length ? new Set() : new Set(pageRows.map((r) => r.id)),
    );
  }

  function download(name: string, content: string, type: string) {
    const blob = new Blob([content], { type });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = name;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  function exportCSV() {
    const headers = ["Id", "Name", "Reference", "Job", "Score", "Recommendation", "Stage", "Applied"];
    const lines = sorted.map((r) =>
      [r.id, r.full_name ?? "", r.candidate_ref, r.job_id, r.score ?? "", r.recommendation ?? "", r.state, r.created_at.slice(0, 10)]
        .map((c) => `"${String(c).replaceAll('"', '""')}"`)
        .join(","),
    );
    download(
      `candidates-${new Date().toISOString().slice(0, 10)}.csv`,
      [headers.join(","), ...lines].join("\n"),
      "text/csv;charset=utf-8;",
    );
  }

  function exportJSON() {
    download(
      `candidates-${new Date().toISOString().slice(0, 10)}.json`,
      JSON.stringify(sorted, null, 2),
      "application/json;charset=utf-8;",
    );
  }

  const animate = !reduced;
  const rowVariants = {
    hidden: { opacity: 0, y: 14, filter: "blur(3px)" },
    visible: {
      opacity: 1,
      y: 0,
      filter: "blur(0px)",
      transition: { type: "spring" as const, stiffness: 400, damping: 26, mass: 0.7 },
    },
  };

  const headCell =
    "text-muted-foreground relative flex shrink-0 items-center gap-1.5 px-3 text-xs font-medium";

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex items-center justify-end gap-2">
        <MenuButton
          open={sortOpen}
          onToggle={() => setSortOpen((v) => !v)}
          icon={<ArrowDownUp className="size-3.5" aria-hidden />}
          label="Sort"
          badge={sortField ? "1" : undefined}
        >
          {(Object.keys(SORT_LABELS) as SortField[]).map((f) => (
            <button
              key={f}
              onClick={() => toggleSort(f)}
              className={`hover:bg-accent flex w-full items-center justify-between px-3.5 py-2 text-left text-sm transition-colors ${
                sortField === f ? "bg-accent/60 font-medium" : ""
              }`}
            >
              {SORT_LABELS[f]}
              {sortField === f && (
                <span className="text-muted-foreground text-xs">
                  {sortOrder === "asc" ? "↑" : "↓"}
                </span>
              )}
            </button>
          ))}
        </MenuButton>

        <MenuButton
          open={exportOpen}
          onToggle={() => setExportOpen((v) => !v)}
          icon={<Download className="size-3.5" aria-hidden />}
          label="Export"
        >
          <button
            onClick={() => {
              exportCSV();
              setExportOpen(false);
            }}
            className="hover:bg-accent w-full px-3.5 py-2 text-left text-sm transition-colors"
          >
            CSV
          </button>
          <button
            onClick={() => {
              exportJSON();
              setExportOpen(false);
            }}
            className="hover:bg-accent w-full border-t px-3.5 py-2 text-left text-sm transition-colors"
          >
            JSON
          </button>
        </MenuButton>
      </div>

      {/* Table */}
      <div className="surface overflow-hidden">
        <div className="overflow-x-auto">
          <div className="min-w-fit">
            {/* Header */}
            <div className="bg-muted/40 flex border-b py-2.5">
              <div
                className="flex shrink-0 items-center justify-center"
                style={{ width: widths.check }}
              >
                <input
                  type="checkbox"
                  aria-label="Select all"
                  className="accent-primary size-4 cursor-pointer rounded"
                  checked={pageRows.length > 0 && selected.size === pageRows.length}
                  onChange={toggleAll}
                />
              </div>
              <div className={headCell} style={{ width: widths.candidate }}>
                <UserRound className="size-3.5 opacity-50" aria-hidden />
                Candidate
              </div>
              <div className={headCell} style={{ width: widths.job }}>
                <Briefcase className="size-3.5 opacity-50" aria-hidden />
                Job
              </div>
              <div className={headCell} style={{ width: widths.score }}>
                <Gauge className="size-3.5 opacity-50" aria-hidden />
                Score
              </div>
              <div className={headCell} style={{ width: widths.stage }}>
                <Layers className="size-3.5 opacity-50" aria-hidden />
                Stage
              </div>
              <div className={headCell} style={{ width: widths.applied }}>
                <CalendarDays className="size-3.5 opacity-50" aria-hidden />
                Applied
              </div>
            </div>

            {/* Rows */}
            <AnimatePresence mode="wait">
              <motion.div
                key={`page-${page}-${sortField}-${sortOrder}`}
                initial={animate ? "hidden" : false}
                animate="visible"
                variants={{
                  visible: { transition: { staggerChildren: 0.035, delayChildren: 0.05 } },
                }}
              >
                {pageRows.map((r) => (
                  <motion.div key={r.id} variants={animate ? rowVariants : undefined}>
                    <div
                      className={`flex border-b py-3 transition-colors duration-150 last:border-b-0 ${
                        selected.has(r.id) ? "bg-accent/70" : "hover:bg-accent/40"
                      }`}
                    >
                      <div
                        className="flex shrink-0 items-center justify-center"
                        style={{ width: widths.check }}
                      >
                        <input
                          type="checkbox"
                          aria-label={`Select ${r.full_name || r.candidate_ref}`}
                          className="accent-primary size-4 cursor-pointer rounded"
                          checked={selected.has(r.id)}
                          onChange={() => toggleRow(r.id)}
                        />
                      </div>
                      <div
                        className="flex min-w-0 shrink-0 flex-col justify-center px-3"
                        style={{ width: widths.candidate }}
                      >
                        <span className="truncate text-sm font-medium">
                          {r.full_name || r.candidate_ref}
                        </span>
                        <span className="text-muted-foreground truncate text-xs">
                          {r.full_name ? r.candidate_ref : `#${r.id}`}
                        </span>
                      </div>
                      <div
                        className="flex shrink-0 items-center px-3 text-sm"
                        style={{ width: widths.job }}
                      >
                        Job #{r.job_id}
                      </div>
                      <div
                        className="flex shrink-0 items-center overflow-hidden px-3"
                        style={{ width: widths.score }}
                      >
                        <ScoreCell score={r.score} recommendation={r.recommendation} />
                      </div>
                      <div
                        className="flex shrink-0 items-center px-3"
                        style={{ width: widths.stage }}
                      >
                        <StateBadge state={r.state as ApplicationState} />
                      </div>
                      <div
                        className="text-muted-foreground flex shrink-0 items-center px-3 text-xs"
                        style={{ width: widths.applied }}
                      >
                        {r.created_at.slice(0, 10)}
                      </div>
                    </div>
                  </motion.div>
                ))}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="text-muted-foreground flex items-center justify-between px-1 text-xs">
        <span>
          {selected.size > 0 ? `${selected.size} selected · ` : ""}
          {sorted.length} candidate{sorted.length === 1 ? "" : "s"}
          {totalPages > 1 ? ` · page ${page} of ${totalPages}` : ""}
        </span>
        {totalPages > 1 && (
          <span className="flex gap-1.5">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="bg-card hover:bg-accent rounded-full border px-3 py-1.5 transition-colors disabled:cursor-not-allowed disabled:opacity-40"
            >
              Previous
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="bg-card hover:bg-accent rounded-full border px-3 py-1.5 transition-colors disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
            </button>
          </span>
        )}
      </div>
    </div>
  );
}
