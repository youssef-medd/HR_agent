"use client";

/**
 * Public application form — the right-hand card of the job page.
 *
 * Styled for the dark public surface (black ground + orange accent), matching
 * the cinematic login rather than the recruiter console's light theme. The CV
 * field is a real drag-and-drop zone; a bare <input type="file"> was the most
 * obviously unfinished element on the page.
 *
 * Deliberately short: availability, salary, notice period and mobility are A5's
 * job during pre-screening, so asking them here would cost completions for
 * data the pipeline collects later anyway.
 */

import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  Brain,
  CheckCircle2,
  FileText,
  Link2,
  Loader2,
  Lock,
  Mail,
  MessageCircle,
  UploadCloud,
  UserRound,
  X,
  type LucideIcon,
} from "lucide-react";
import { toast } from "sonner";

import { cn } from "@/lib/utils";

// Images included because A3 OCRs a photographed / scanned CV.
const ACCEPT = ".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp";
const MAX_BYTES = 10 * 1024 * 1024;

const fieldClass =
  "w-full rounded-xl border border-white/10 bg-white/[0.03] py-2.5 pr-4 pl-10 text-sm " +
  "text-white placeholder:text-white/25 transition-colors duration-200 " +
  "focus:border-primary/50 focus:bg-white/[0.05] focus:outline-none";

function Field({
  id,
  label,
  icon: Icon,
  required,
  hint,
  fromCv,
  ...input
}: {
  id: string;
  label: string;
  icon: LucideIcon;
  required?: boolean;
  hint?: string;
  /** Marks a value that was read out of the CV rather than typed. */
  fromCv?: boolean;
} & React.ComponentPropsWithoutRef<"input">) {
  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-sm font-medium text-white/80">
        {label}{" "}
        {required ? (
          <span className="text-primary" aria-hidden>
            *
          </span>
        ) : (
          <span className="font-normal text-white/35">(optional)</span>
        )}
        {fromCv && (
          <span className="border-primary/30 bg-primary/10 text-primary ml-2 rounded-full border px-2 py-0.5 text-[10px] font-medium">
            from your CV
          </span>
        )}
      </label>
      <div className="relative">
        <Icon
          className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-white/30"
          aria-hidden
        />
        <input id={id} required={required} className={fieldClass} {...input} />
      </div>
      {hint && <p className="mt-1.5 text-xs text-white/35">{hint}</p>}
    </div>
  );
}

function formatSize(bytes: number): string {
  return bytes < 1024 * 1024
    ? `${Math.round(bytes / 1024)} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ApplyForm({ jobId, jobTitle }: { jobId: number; jobTitle: string }) {
  const [pending, setPending] = React.useState(false);
  const [done, setDone] = React.useState(false);
  const [appId, setAppId] = React.useState<number | null>(null);
  const [file, setFile] = React.useState<File | null>(null);
  const [dragging, setDragging] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // Fields are controlled so attaching a CV can fill them in.
  const [fields, setFields] = React.useState({
    full_name: "",
    email: "",
    phone: "",
    link: "",
  });
  const [reading, setReading] = React.useState(false);
  const [prefilled, setPrefilled] = React.useState<string[]>([]);

  const set = (key: keyof typeof fields) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setFields((f) => ({ ...f, [key]: e.target.value }));
    // Once the candidate edits a field it is theirs, not ours.
    setPrefilled((p) => p.filter((k) => k !== key));
  };

  /**
   * Read the CV and fill whatever the candidate has not already typed.
   * Never overwrites their own input, and never blocks: a failed read just
   * leaves the form as it was.
   */
  async function prefillFrom(cv: File) {
    setReading(true);
    try {
      const body = new FormData();
      body.set("file", cv);
      const res = await fetch("/api/public/prefill", { method: "POST", body });
      if (!res.ok) return;
      const data = (await res.json()) as Partial<typeof fields>;
      const filled: string[] = [];
      setFields((current) => {
        const next = { ...current };
        for (const key of ["full_name", "email", "phone", "link"] as const) {
          const value = (data[key] ?? "").trim();
          if (value && !current[key].trim()) {
            next[key] = value;
            filled.push(key);
          }
        }
        return next;
      });
      setPrefilled(filled);
      if (filled.length > 0) {
        toast.success(`Filled ${filled.length} field${filled.length > 1 ? "s" : ""} from your CV`);
      }
    } catch {
      // Silent: prefill is a convenience.
    } finally {
      setReading(false);
    }
  }

  function acceptFile(candidate: File | undefined | null) {
    if (!candidate) return;
    const ok = ACCEPT.split(",").some((ext) =>
      candidate.name.toLowerCase().endsWith(ext),
    );
    if (!ok) {
      toast.error("Unsupported file type — use PDF, DOCX, JPG or PNG");
      return;
    }
    if (candidate.size > MAX_BYTES) {
      toast.error("That file is over 10 MB");
      return;
    }
    setFile(candidate);
    void prefillFrom(candidate);
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending) return;
    if (!file) {
      toast.error("Attach your CV first");
      return;
    }

    const data = new FormData();
    data.set("job_id", String(jobId));
    data.set("file", file);
    data.set("full_name", fields.full_name);
    data.set("email", fields.email);
    data.set("phone", fields.phone);
    data.set("link", fields.link);

    setPending(true);
    const res = await fetch("/api/public/apply", { method: "POST", body: data });
    setPending(false);

    if (!res.ok) {
      const err = await res.json().catch(() => null);
      toast.error(err?.detail ?? err?.error ?? `Submission failed (${res.status})`);
      return;
    }

    const body = await res.json().catch(() => null);
    setAppId(typeof body?.application_id === "number" ? body.application_id : null);
    setDone(true);
  }

  if (done) {
    return (
      <div className="flex flex-col items-center gap-4 py-12 text-center">
        <span className="flex size-14 items-center justify-center rounded-2xl bg-emerald-500/10">
          <CheckCircle2 className="size-7 text-emerald-400" />
        </span>
        <div>
          <p className="font-heading text-xl font-semibold text-white">
            Application received
          </p>
          <p className="mt-1.5 text-sm text-white/50">
            Thanks for applying to{" "}
            <span className="text-white/80">{jobTitle}</span>. We&apos;ll review your CV
            and be in touch.
          </p>
        </div>
        {appId !== null && (
          <div className="w-full rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <p className="text-xs tracking-wide text-white/40 uppercase">
              Your reference
            </p>
            <p className="font-heading text-primary mt-1 text-2xl font-semibold">
              #{appId}
            </p>
            <Link
              href="/portal"
              className="text-primary mt-3 inline-flex items-center gap-1.5 text-sm hover:underline"
            >
              Track your application <ArrowRight className="size-3.5" />
            </Link>
          </div>
        )}
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-5">
      <Field
        id="full_name"
        name="full_name"
        label="Full name"
        icon={UserRound}
        required
        placeholder="Jane Doe"
        autoComplete="name"
        value={fields.full_name}
        onChange={set("full_name")}
        fromCv={prefilled.includes("full_name")}
      />
      <Field
        id="email"
        name="email"
        type="email"
        label="Email"
        icon={Mail}
        required
        placeholder="jane@example.com"
        autoComplete="email"
        value={fields.email}
        onChange={set("email")}
        fromCv={prefilled.includes("email")}
      />

      <div className="grid gap-5 sm:grid-cols-2">
        <Field
          id="phone"
          name="phone"
          type="tel"
          label="WhatsApp number"
          icon={MessageCircle}
          placeholder="+216 12 345 678"
          autoComplete="tel"
          value={fields.phone}
          onChange={set("phone")}
          fromCv={prefilled.includes("phone")}
        />
        <Field
          id="link"
          name="link"
          type="url"
          label="LinkedIn / Portfolio"
          icon={Link2}
          placeholder="https://linkedin.com/in/yourprofile"
          autoComplete="url"
          value={fields.link}
          onChange={set("link")}
          fromCv={prefilled.includes("link")}
        />
      </div>

      {/* CV dropzone */}
      <div>
        <label className="mb-2 block text-sm font-medium text-white/80">
          CV / Resume{" "}
          <span className="text-primary" aria-hidden>
            *
          </span>
        </label>

        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="sr-only"
          onChange={(e) => acceptFile(e.target.files?.[0])}
        />

        {file ? (
          <div className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <span className="bg-primary/10 flex size-10 shrink-0 items-center justify-center rounded-lg">
              <FileText className="text-primary size-5" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-white">{file.name}</p>
              <p className="text-xs text-white/40">
                {reading ? "Reading your details…" : formatSize(file.size)}
              </p>
            </div>
            {reading ? (
              <Loader2 className="text-primary size-5 shrink-0 animate-spin" aria-hidden />
            ) : (
              <CheckCircle2 className="size-5 shrink-0 text-emerald-400" aria-hidden />
            )}
            <button
              type="button"
              onClick={() => {
                setFile(null);
                if (inputRef.current) inputRef.current.value = "";
              }}
              className="text-white/30 transition-colors hover:text-white"
              aria-label="Remove file"
            >
              <X className="size-4" />
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              acceptFile(e.dataTransfer.files?.[0]);
            }}
            className={cn(
              "flex w-full flex-col items-center gap-2 rounded-xl border border-dashed px-6 py-10 text-center transition-colors duration-200",
              dragging
                ? "border-primary bg-primary/[0.07]"
                : "border-primary/35 bg-white/[0.02] hover:border-primary/60 hover:bg-white/[0.04]",
            )}
          >
            <UploadCloud className="text-primary size-8" aria-hidden />
            <span className="font-heading text-base font-semibold text-white">
              Drag &amp; drop your CV here
            </span>
            <span className="text-sm text-white/45">
              or <span className="text-primary underline">browse files</span>
            </span>
            <span className="text-xs text-white/30">
              PDF, DOCX, JPG or PNG · Max 10 MB
            </span>
          </button>
        )}
      </div>

      {/* AI transparency notice (spec §7) */}
      <div className="flex gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-4">
        <Brain className="text-primary mt-0.5 size-5 shrink-0" aria-hidden />
        <div>
          <p className="text-sm font-medium text-white">AI-assisted recruitment</p>
          <p className="mt-1 text-xs leading-relaxed text-white/45">
            Your application may be reviewed by our AI assistant to help analyse your
            CV and match your skills. If shortlisted, you may be invited to a short AI
            pre-screening conversation. All final decisions are made by a human
            recruiter.
          </p>
        </div>
      </div>

      <button
        type="submit"
        disabled={pending}
        className="from-primary group mt-1 flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r to-[#ff8a33] py-3.5 text-sm font-semibold text-white shadow-[0_8px_30px_rgba(255,107,0,0.25)] transition-all duration-200 hover:shadow-[0_8px_36px_rgba(255,107,0,0.4)] disabled:opacity-60"
      >
        {pending ? (
          <>
            <Loader2 className="size-4 animate-spin" /> Submitting…
          </>
        ) : (
          <>
            Submit application
            <ArrowRight className="size-4 transition-transform duration-200 group-hover:translate-x-1" />
          </>
        )}
      </button>

      <p className="flex items-center justify-center gap-1.5 text-center text-xs text-white/35">
        <Lock className="size-3" aria-hidden />
        By applying, you agree to the processing of your data. You can request
        deletion any time from the portal.
      </p>
    </form>
  );
}
