import Link from "next/link";
import { notFound } from "next/navigation";
import {
  ArrowLeft,
  Briefcase,
  Building2,
  Check,
  Languages,
  MapPin,
  Shield,
  Sparkles,
  TrendingUp,
  UserRound,
  type LucideIcon,
} from "lucide-react";

import { ApplyForm } from "@/components/apply/apply-form";
import { GlassCard, PublicShell } from "@/components/apply/public-shell";
import { API_URL } from "@/lib/api/client";

export const dynamic = "force-dynamic";

interface PublicJob {
  id: number;
  title: string;
  department: string | null;
  location: string | null;
  description: string;
  // A1's structured JobSpec (public slice — no eliminatory criteria or weights).
  seniority: string;
  missions: string[];
  must_have: string[];
  nice_to_have: string[];
  languages: string[];
}

async function getJob(jobId: string): Promise<PublicJob | null> {
  try {
    const res = await fetch(`${API_URL}/public/jobs/${jobId}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as PublicJob;
  } catch {
    return null;
  }
}

/**
 * A1 fills unknown spec fields with placeholder prose ("Not specified", "N/A")
 * rather than leaving them empty. Rendering those verbatim looks broken, so
 * treat them as absent and drop the section entirely.
 */
const PLACEHOLDERS = new Set(["not specified", "n/a", "na", "unknown", "none", "-"]);

function real(value: string | null | undefined): string {
  const v = (value ?? "").trim();
  return PLACEHOLDERS.has(v.toLowerCase()) ? "" : v;
}

/**
 * A1's `must_have` mixes short tech tokens ("PyTorch") with full requirement
 * sentences ("Proven experience building AI/ML models"). Pills suit the first
 * kind only — a sentence in a pill is a cramped paragraph — so the long ones
 * are rendered as a proper list instead.
 */
function isTag(s: string): boolean {
  const t = s.trim();
  return t.length > 0 && t.length <= 22 && t.split(/\s+/).length <= 3;
}

function MetaItem({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <div className="flex gap-3">
      <Icon className="text-primary mt-0.5 size-4 shrink-0" aria-hidden />
      <div>
        <p className="text-sm font-medium text-white">{label}</p>
        <p className="mt-0.5 text-sm text-white/45">{value}</p>
      </div>
    </div>
  );
}

export default async function ApplyJobPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = await params;
  const job = await getJob(jobId);
  if (!job) notFound();

  // Short tokens become pills; anything sentence-length reads as a requirement.
  const all = [...job.must_have, ...job.nice_to_have];
  const tags = all.filter(isTag).slice(0, 12);
  const requirements = all.filter((s) => !isTag(s));
  const seniority = real(job.seniority);
  const location = real(job.location);
  const department = real(job.department);

  return (
    <PublicShell>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1fr)]">
        {/* ---------- Left: the role ---------- */}
        <GlassCard className="p-8">
          <Link
            href="/apply"
            className="mb-7 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-white/60 transition-colors duration-200 hover:border-white/25 hover:text-white"
          >
            <ArrowLeft className="size-3.5" /> Back to jobs
          </Link>

          {seniority && (
            <span className="border-primary/40 bg-primary/10 text-primary mb-5 inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium capitalize">
              <Briefcase className="size-3.5" aria-hidden />
              {seniority}
            </span>
          )}

          <h1 className="font-heading text-4xl font-semibold tracking-tight text-white">
            {job.title}
          </h1>

          <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-white/55">
            <span className="inline-flex items-center gap-1.5">
              <Building2 className="text-primary size-4" aria-hidden /> Welyne
            </span>
            {location && (
              <span className="inline-flex items-center gap-1.5">
                <MapPin className="text-primary size-4" aria-hidden /> {location}
              </span>
            )}
            {seniority && (
              <span className="inline-flex items-center gap-1.5 capitalize">
                <TrendingUp className="text-primary size-4" aria-hidden />{" "}
                {seniority}
              </span>
            )}
          </div>

          {job.description && (
            <p className="mt-6 text-sm leading-relaxed whitespace-pre-wrap text-white/60">
              {job.description}
            </p>
          )}

          {(tags.length > 0 || requirements.length > 0) && (
            <hr className="my-7 border-white/[0.08]" />
          )}

          {tags.length > 0 && (
            <>
              <p className="mb-3 text-sm font-medium text-white">Key technologies</p>
              <div className="flex flex-wrap gap-2">
                {tags.map((s) => (
                  <span
                    key={s}
                    className="rounded-lg border border-white/12 bg-white/[0.08] px-3 py-1.5 text-xs font-medium text-white/85"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </>
          )}

          {requirements.length > 0 && (
            <div className={tags.length > 0 ? "mt-6" : ""}>
              <p className="mb-3 text-sm font-medium text-white">What we&apos;re looking for</p>
              <ul className="space-y-2">
                {requirements.slice(0, 8).map((r) => (
                  <li
                    key={r}
                    className="flex gap-2.5 text-sm leading-relaxed text-white/60"
                  >
                    <Check className="text-primary mt-0.5 size-4 shrink-0" aria-hidden />
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-7 grid gap-5 sm:grid-cols-2">
            {seniority && (
              <MetaItem icon={TrendingUp} label="Experience" value={seniority} />
            )}
            {location && (
              <MetaItem icon={MapPin} label="Location" value={location} />
            )}
            {department && (
              <MetaItem icon={Building2} label="Department" value={department} />
            )}
            {job.languages.length > 0 && (
              <MetaItem
                icon={Languages}
                label="Languages"
                value={job.languages.join(" · ")}
              />
            )}
          </div>

          {job.missions.length > 0 && (
            <div className="border-primary/25 bg-primary/[0.04] mt-7 rounded-2xl border p-5">
              <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
                <Sparkles className="text-primary size-4" aria-hidden />
                What you&apos;ll do
              </p>
              <ul className="space-y-2">
                {job.missions.slice(0, 5).map((m) => (
                  <li
                    key={m}
                    className="flex gap-2.5 text-sm leading-relaxed text-white/60"
                  >
                    <span className="bg-primary mt-1.5 size-1 shrink-0 rounded-full" />
                    {m}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </GlassCard>

        {/* ---------- Right: the application ---------- */}
        <GlassCard className="p-8">
          <h2 className="font-heading text-3xl font-semibold tracking-tight text-white">
            Apply for this position
          </h2>
          <p className="mt-2 mb-7 text-sm text-white/45">
            Fill in your details and upload your CV to get started.
          </p>
          <ApplyForm jobId={job.id} jobTitle={job.title} />
        </GlassCard>
      </div>

      {/* ---------- Trust bar ---------- */}
      <GlassCard className="mt-6 grid gap-6 p-7 sm:grid-cols-2 lg:grid-cols-4">
        {[
          {
            icon: Sparkles,
            title: "AI-powered process",
            body: "Smart screening & matching",
          },
          {
            icon: UserRound,
            title: "Human decisions",
            body: "People make the final call",
          },
          { icon: Shield, title: "Your data is safe", body: "We respect your privacy" },
          {
            icon: Briefcase,
            title: "Transparent communication",
            body: "We keep you informed",
          },
        ].map(({ icon: Icon, title, body }) => (
          <div key={title} className="flex items-center gap-3">
            <Icon className="text-primary size-6 shrink-0" aria-hidden />
            <div>
              <p className="text-sm font-medium text-white">{title}</p>
              <p className="text-xs text-white/40">{body}</p>
            </div>
          </div>
        ))}
      </GlassCard>
    </PublicShell>
  );
}
