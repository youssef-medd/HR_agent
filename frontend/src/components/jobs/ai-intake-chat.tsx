"use client";

import * as React from "react";
import { Check, Loader2, Paperclip, SendHorizonal, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAutoResizeTextarea } from "@/hooks/use-auto-resize-textarea";
import { cn } from "@/lib/utils";
import type { IntakeTurn, JobIntake } from "@/lib/api/client";

type Msg = { role: "assistant" | "user"; text: string };

const OPENER =
  "Tell me about the role you want to hire for — in your own words. I'll ask a couple of questions, then draft the full job for you to review.";

const SUGGESTIONS = [
  "ML engineer, production PyTorch, 3+ years",
  "Senior backend engineer — Python, PostgreSQL, Tunis",
  "Product designer, B2B SaaS, hybrid",
];

function AssistantAvatar() {
  return (
    <span className="bg-primary/10 text-primary flex size-7 shrink-0 items-center justify-center rounded-full">
      <Sparkles className="size-3.5" />
    </span>
  );
}

function TypingDots() {
  return (
    <span className="flex items-center gap-1 px-1 py-1">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="bg-muted-foreground/50 size-1.5 animate-bounce rounded-full"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  );
}

function WeightBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="grid grid-cols-[4.5rem_1fr_1.75rem] items-center gap-2">
      <span className="text-muted-foreground text-[11px] capitalize">{label}</span>
      <div className="bg-muted h-1.5 overflow-hidden rounded-full">
        <div className="bg-primary h-full rounded-full" style={{ width: `${value}%` }} />
      </div>
      <span className="text-right text-[11px] tabular-nums">{value}</span>
    </div>
  );
}

export function AiIntakeChat({ onCreated }: { onCreated: (jobId: number) => void }) {
  const [messages, setMessages] = React.useState<Msg[]>([{ role: "assistant", text: OPENER }]);
  const [input, setInput] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [draft, setDraft] = React.useState<{ title: string; intake: JobIntake } | null>(null);
  const [saving, setSaving] = React.useState(false);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = React.useState(false);
  const { textareaRef, adjustHeight } = useAutoResizeTextarea({ minHeight: 48, maxHeight: 160 });

  React.useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy, draft]);

  async function send(text: string) {
    const t = text.trim();
    if (!t || busy) return;
    const convo: Msg[] = [...messages, { role: "user", text: t }];
    setMessages(convo);
    setInput("");
    adjustHeight(true);
    setBusy(true);
    try {
      // Only real dialogue turns go to the model (skip the static opener).
      const forModel = convo.filter((m, i) => !(i === 0 && m.role === "assistant"));
      const res = await fetch("/api/jobs/intake/converse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: forModel }),
      });
      if (!res.ok) {
        toast.error(`Failed (${res.status})`);
        return;
      }
      const turn = (await res.json()) as IntakeTurn;
      if (turn.done && turn.intake) {
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            text: `Here's the draft for “${turn.title || "the role"}”. Review it below — shall I create and save it?`,
          },
        ]);
        setDraft({ title: turn.title || "New role", intake: turn.intake });
      } else {
        setMessages((m) => [...m, { role: "assistant", text: turn.question || "Tell me more?" }]);
      }
    } finally {
      setBusy(false);
    }
  }

  /** Attach a JD file: extract its text, then feed it to the AI as the brief. */
  async function uploadJd(file: File) {
    if (uploading || busy) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.set("file", file);
      const res = await fetch("/api/jobs/intake/extract", { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail ?? `Could not read ${file.name}`);
        return;
      }
      const { text } = (await res.json()) as { text: string };
      // Show the attachment in the thread, send the extracted text to the model.
      const convo: Msg[] = [
        ...messages,
        { role: "user", text: `📎 ${file.name}` },
      ];
      setMessages(convo);
      setBusy(true);
      try {
        const forModel = [
          ...convo
            .filter((m, i) => !(i === 0 && m.role === "assistant"))
            .slice(0, -1),
          { role: "user" as const, text: `Here is the job description:\n\n${text}` },
        ];
        const turn = await fetch("/api/jobs/intake/converse", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages: forModel }),
        }).then((r) => (r.ok ? (r.json() as Promise<IntakeTurn>) : null));
        if (!turn) {
          toast.error("The assistant could not process that file");
          return;
        }
        if (turn.done && turn.intake) {
          setMessages((m) => [
            ...m,
            {
              role: "assistant",
              text: `Read “${file.name}”. Here's the draft for “${turn.title || "the role"}” — shall I create and save it?`,
            },
          ]);
          setDraft({ title: turn.title || "New role", intake: turn.intake });
        } else {
          setMessages((m) => [
            ...m,
            { role: "assistant", text: turn.question || "Got the file — tell me more?" },
          ]);
        }
      } finally {
        setBusy(false);
      }
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function saveJob() {
    if (!draft) return;
    setSaving(true);
    const res = await fetch("/api/jobs/intake/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: draft.title, intake: draft.intake }),
    });
    setSaving(false);
    if (!res.ok) {
      toast.error("Could not create the job");
      return;
    }
    const body = (await res.json()) as { job_id: number };
    toast.success(`Job created — “${draft.title}”`);
    onCreated(body.job_id);
  }

  const canSend = input.trim().length > 0 && !busy;
  const showSuggestions = messages.length === 1 && !busy;

  return (
    <div className="flex h-[58vh] flex-col">
      {/* Conversation */}
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-0.5 py-2">
        {messages.map((m, i) =>
          m.role === "assistant" ? (
            <div key={i} className="flex items-start gap-2.5">
              <AssistantAvatar />
              <div className="bg-muted text-foreground max-w-[85%] rounded-2xl rounded-tl-sm px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap">
                {m.text}
              </div>
            </div>
          ) : (
            <div key={i} className="flex justify-end">
              <div className="bg-primary text-primary-foreground max-w-[85%] rounded-2xl rounded-br-sm px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-wrap">
                {m.text}
              </div>
            </div>
          ),
        )}

        {busy && (
          <div className="flex items-start gap-2.5">
            <AssistantAvatar />
            <div className="bg-muted rounded-2xl rounded-tl-sm px-3 py-2">
              <TypingDots />
            </div>
          </div>
        )}

        {/* Draft proposal */}
        {draft && (
          <div className="surface ml-9 space-y-3 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-heading text-sm font-semibold">{draft.title}</p>
                {draft.intake.spec.seniority && (
                  <p className="text-muted-foreground text-xs capitalize">
                    {draft.intake.spec.seniority}
                    {draft.intake.spec.location ? ` · ${draft.intake.spec.location}` : ""}
                  </p>
                )}
              </div>
              <span className="bg-primary/10 text-primary rounded-full px-2 py-0.5 text-[10px] font-medium">
                AI draft
              </span>
            </div>

            {draft.intake.spec.must_have.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {draft.intake.spec.must_have.slice(0, 8).map((s, i) => (
                  <span key={i} className="bg-muted rounded-full px-2.5 py-1 text-[11px]">
                    {s}
                  </span>
                ))}
              </div>
            )}

            {draft.intake.spec.eliminatory_criteria.length > 0 && (
              <p className="text-muted-foreground text-[11px]">
                <span className="font-medium">Hard filters:</span>{" "}
                {draft.intake.spec.eliminatory_criteria.join(" · ")}
              </p>
            )}

            <div className="space-y-1 border-t pt-2.5">
              <p className="eyebrow mb-1.5">Scoring weights</p>
              <WeightBar label="skills" value={draft.intake.weights.skills} />
              <WeightBar label="experience" value={draft.intake.weights.experience} />
              <WeightBar label="education" value={draft.intake.weights.education} />
              <WeightBar label="sector" value={draft.intake.weights.sector} />
            </div>

            <div className="flex gap-2 pt-1">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="flex-1"
                onClick={() => {
                  setDraft(null);
                  setMessages((m) => [
                    ...m,
                    { role: "assistant", text: "Sure — what should I change?" },
                  ]);
                }}
              >
                Keep refining
              </Button>
              <Button type="button" size="sm" onClick={saveJob} disabled={saving} className="flex-1 gap-1">
                {saving ? <Loader2 className="size-4 animate-spin" /> : <Check className="size-4" />}
                Create &amp; save
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Suggestions */}
      {showSuggestions && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => send(s)}
              className="border-border hover:border-primary hover:text-foreground text-muted-foreground rounded-full border px-3 py-1.5 text-xs transition-colors"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Composer */}
      <div
        className={cn(
          "from-muted/60 relative rounded-2xl border bg-gradient-to-b to-transparent transition-colors",
          canSend && "border-primary/40",
        )}
      >
        <Textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            adjustHeight();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
          disabled={busy}
          placeholder="Describe the role, or attach a job description…"
          rows={1}
          className="max-h-40 min-h-12 resize-none border-none bg-transparent py-3.5 pr-24 pl-4 text-sm shadow-none focus-visible:border-none focus-visible:ring-0 dark:bg-transparent"
        />

        <div className="absolute right-2.5 bottom-2.5 flex items-center gap-1.5">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt,.md"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) uploadJd(f);
            }}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={busy || uploading}
            aria-label="Attach a job description (PDF, DOCX, TXT)"
            title="Attach a job description (PDF, DOCX, TXT)"
            className="text-muted-foreground hover:bg-muted hover:text-foreground flex size-8 items-center justify-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          >
            {uploading ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Paperclip className="size-4" />
            )}
          </button>

          <button
            type="button"
            onClick={() => send(input)}
            disabled={!canSend}
            aria-label="Send message"
            className={cn(
              "flex size-8 items-center justify-center rounded-full transition-colors",
              canSend
                ? "bg-primary text-primary-foreground hover:opacity-90"
                : "bg-muted text-muted-foreground cursor-not-allowed",
            )}
          >
            {busy ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <SendHorizonal className="size-4" />
            )}
          </button>
        </div>
      </div>

      <p className="text-muted-foreground mt-2 flex items-center gap-1.5 text-[10px]">
        <Sparkles className="size-3" />
        AI assistant · <kbd className="font-sans">Enter</kbd> to send,{" "}
        <kbd className="font-sans">Shift+Enter</kbd> for a new line. A human confirms before anything
        is saved.
      </p>
    </div>
  );
}
