"use client";

/**
 * Searchable open-roles list.
 *
 * The list is fetched on the server and filtered here — the volume of open
 * roles is small enough that a round trip per keystroke would be slower and
 * noisier than filtering in place.
 */

import * as React from "react";
import Link from "next/link";
import { ArrowRight, Briefcase, MapPin, Search, TrendingUp, X } from "lucide-react";

import { GlassCard } from "@/components/apply/public-shell";
import { cn } from "@/lib/utils";

export interface PublicJob {
  id: number;
  title: string;
  department: string | null;
  location: string | null;
  description: string;
  seniority: string;
  must_have: string[];
  nice_to_have: string[];
}

// A1 writes placeholder prose ("Not specified") into unknown spec fields;
// rendering it verbatim looks broken, so treat those as absent.
const PLACEHOLDERS = new Set(["not specified", "n/a", "na", "unknown", "none", "-"]);

function real(value: string | null | undefined): string {
  const v = (value ?? "").trim();
  return PLACEHOLDERS.has(v.toLowerCase()) ? "" : v;
}

/**
 * A1's `must_have` mixes short tech tokens ("PyTorch") with full requirement
 * sentences ("Proven experience building AI/ML models"). Only the former read
 * as pills — a sentence in a pill is just a cramped paragraph — so the long
 * ones are counted instead of rendered.
 */
function isTag(s: string): boolean {
  const t = s.trim();
  return t.length > 0 && t.length <= 22 && t.split(/\s+/).length <= 3;
}

function Meta({
  icon: Icon,
  children,
}: {
  icon: typeof MapPin;
  children: React.ReactNode;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-lg bg-white/[0.06] px-2.5 py-1 text-xs text-white/70">
      <Icon className="text-primary size-3.5" aria-hidden />
      {children}
    </span>
  );
}

export function JobSearch({ jobs }: { jobs: PublicJob[] }) {
  const [query, setQuery] = React.useState("");

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return jobs;
    // Match across everything a candidate might type: role, team, city, stack.
    return jobs.filter((j) =>
      [
        j.title,
        j.department ?? "",
        j.location ?? "",
        j.seniority,
        j.description,
        ...j.must_have,
        ...j.nice_to_have,
      ]
        .join(" ")
        .toLowerCase()
        .includes(q),
    );
  }, [jobs, query]);

  return (
    <>
      <div className="relative mx-auto mb-8 max-w-xl">
        <Search
          className="pointer-events-none absolute top-1/2 left-4 size-4 -translate-y-1/2 text-white/35"
          aria-hidden
        />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by role, team, location or skill…"
          aria-label="Search open roles"
          className="focus:border-primary/50 w-full rounded-full border border-white/12 bg-white/[0.06] py-3 pr-10 pl-11 text-sm text-white shadow-[0_4px_24px_rgba(0,0,0,0.4)] backdrop-blur-xl transition-colors placeholder:text-white/30 focus:bg-white/[0.09] focus:outline-none"
        />
        {query && (
          <button
            type="button"
            onClick={() => setQuery("")}
            aria-label="Clear search"
            className="absolute top-1/2 right-4 -translate-y-1/2 text-white/35 transition-colors hover:text-white"
          >
            <X className="size-4" />
          </button>
        )}
      </div>

      {query && (
        <p className="mb-4 text-center text-xs text-white/40">
          {filtered.length} {filtered.length === 1 ? "role" : "roles"} matching “
          {query}”
        </p>
      )}

      {filtered.length === 0 ? (
        <GlassCard className="py-16 text-center">
          <p className="text-sm text-white/50">
            {jobs.length === 0
              ? "No open roles right now. Please check back soon."
              : "No roles match that search."}
          </p>
          {query && jobs.length > 0 && (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="text-primary mt-3 text-sm hover:underline"
            >
              Clear search
            </button>
          )}
        </GlassCard>
      ) : (
        <div className="grid gap-5">
          {filtered.map((job) => {
            const seniority = real(job.seniority);
            const location = real(job.location);
            const department = real(job.department);
            const all = [...job.must_have, ...job.nice_to_have];
            const tags = all.filter(isTag).slice(0, 6);
            const extra = all.length - tags.length;

            return (
              <Link key={job.id} href={`/apply/${job.id}`} className="group block">
                <div
                  className={cn(
                    "relative overflow-hidden rounded-3xl border border-white/12 p-7 transition-all duration-300",
                    "bg-gradient-to-br from-white/[0.10] via-white/[0.06] to-white/[0.03]",
                    "shadow-[0_8px_40px_rgba(0,0,0,0.45)] backdrop-blur-xl",
                    "hover:border-primary/45 hover:-translate-y-0.5",
                    "hover:shadow-[0_16px_50px_rgba(255,107,0,0.16)]",
                  )}
                >
                  {/* Warm wash that blooms in on hover */}
                  <span
                    aria-hidden
                    className="from-primary/[0.13] pointer-events-none absolute inset-0 bg-gradient-to-br via-transparent to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100"
                  />
                  {/* Accent hairline along the top edge */}
                  <span
                    aria-hidden
                    className="via-primary pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-70"
                  />

                  <div className="relative flex flex-wrap items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-3">
                        <h2 className="font-heading text-2xl font-semibold tracking-tight text-white">
                          {job.title}
                        </h2>
                        {seniority && (
                          <span className="border-primary/40 bg-primary/15 text-primary rounded-full border px-2.5 py-0.5 text-[11px] font-medium capitalize">
                            {seniority}
                          </span>
                        )}
                      </div>

                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        {department && <Meta icon={Briefcase}>{department}</Meta>}
                        {location && <Meta icon={MapPin}>{location}</Meta>}
                        {seniority && <Meta icon={TrendingUp}>{seniority}</Meta>}
                      </div>

                      {job.description && (
                        <p className="mt-4 line-clamp-2 text-sm leading-relaxed text-white/55">
                          {job.description}
                        </p>
                      )}

                      {(tags.length > 0 || extra > 0) && (
                        <div className="mt-5 flex flex-wrap items-center gap-2">
                          {tags.map((t) => (
                            <span
                              key={t}
                              className="group-hover:border-primary/30 rounded-lg border border-white/12 bg-white/[0.08] px-2.5 py-1 text-xs font-medium text-white/85 transition-colors"
                            >
                              {t}
                            </span>
                          ))}
                          {extra > 0 && (
                            <span className="text-xs text-white/40">
                              +{extra} {extra === 1 ? "requirement" : "requirements"}
                            </span>
                          )}
                        </div>
                      )}
                    </div>

                    <span className="text-primary group-hover:bg-primary/10 inline-flex shrink-0 items-center gap-1.5 rounded-full border border-transparent px-3 py-1.5 text-sm font-medium transition-colors">
                      View role
                      <ArrowRight
                        className="size-4 transition-transform duration-200 group-hover:translate-x-1"
                        aria-hidden
                      />
                    </span>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}
