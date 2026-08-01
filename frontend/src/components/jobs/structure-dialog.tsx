"use client";

import * as React from "react";
import { Check, Copy, Loader2, Save, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { IntakeQuestion, IntakeTurn, JobIntake } from "@/lib/api/client";

type Mode = "chat" | "description" | "brief" | "upload" | "questions";
type ChatMsg = { role: "assistant" | "user"; text: string };

function CopyBtn({ text }: { text: string }) {
  const [done, setDone] = React.useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      }}
      className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs"
    >
      {done ? <Check className="size-3.5 text-emerald-500" /> : <Copy className="size-3.5" />}
      {done ? "Copied" : "Copy"}
    </button>
  );
}

const WEIGHT_KEYS: (keyof JobIntake["weights"])[] = [
  "skills",
  "experience",
  "education",
  "sector",
];

export function StructureDialog({
  jobId,
  jobTitle,
  open: openProp,
  onOpenChange,
  hideTrigger = false,
  autorun = false,
  initialBrief = "",
}: {
  jobId: number;
  jobTitle: string;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  hideTrigger?: boolean;
  autorun?: boolean;
  initialBrief?: string;
}) {
  const [openState, setOpenState] = React.useState(false);
  const open = openProp ?? openState;
  const setOpen = onOpenChange ?? setOpenState;
  const [loading, setLoading] = React.useState(false);
  const ranRef = React.useRef(false);
  const [saving, setSaving] = React.useState(false);
  const [data, setData] = React.useState<JobIntake | null>(null);
  const [mode, setMode] = React.useState<Mode>("chat");
  const [brief, setBrief] = React.useState("");
  const [questions, setQuestions] = React.useState<IntakeQuestion[]>([]);
  const [answers, setAnswers] = React.useState<Record<string, string>>({});
  // Conversational intake state
  const [chat, setChat] = React.useState<ChatMsg[]>([]);
  const [chatInput, setChatInput] = React.useState("");
  const [chatBusy, setChatBusy] = React.useState(false);

  const converse = React.useCallback(
    async (messages: ChatMsg[]) => {
      setChatBusy(true);
      try {
        const res = await fetch(`/api/jobs/${jobId}/intake/converse`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages }),
        });
        if (!res.ok) {
          toast.error(`Failed (${res.status})`);
          return;
        }
        const turn = (await res.json()) as IntakeTurn;
        if (turn.done && turn.intake) {
          setChat((c) => [...c, { role: "assistant", text: "Great — here's the draft to review." }]);
          setData(turn.intake);
        } else {
          setChat((c) => [...c, { role: "assistant", text: turn.question || "Tell me more?" }]);
        }
      } finally {
        setChatBusy(false);
      }
    },
    [jobId],
  );

  async function sendChat(text: string) {
    const t = text.trim();
    if (!t || chatBusy) return;
    const next: ChatMsg[] = [...chat, { role: "user", text: t }];
    setChat(next);
    setChatInput("");
    await converse(next);
  }

  React.useEffect(() => {
    if (open && questions.length === 0) {
      fetch("/api/jobs/intake/questions")
        .then((r) => (r.ok ? r.json() : []))
        .then((qs: IntakeQuestion[]) => setQuestions(qs))
        .catch(() => {});
    }
  }, [open, questions.length]);

  async function run() {
    setLoading(true);
    setData(null);
    try {
      let res: Response;
      if (mode === "upload") {
        const input = document.getElementById("jd-file") as HTMLInputElement | null;
        const file = input?.files?.[0];
        if (!file) {
          toast.error("Choose a file first");
          return;
        }
        const form = new FormData();
        form.set("file", file);
        res = await fetch(`/api/jobs/${jobId}/structure/upload`, { method: "POST", body: form });
      } else {
        const payload =
          mode === "brief"
            ? { brief }
            : mode === "questions"
              ? { answers }
              : {};
        res = await fetch(`/api/jobs/${jobId}/structure`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail ?? err?.error ?? `Failed (${res.status})`);
        return;
      }
      setData((await res.json()) as JobIntake);
    } finally {
      setLoading(false);
    }
  }

  async function save() {
    if (!data) return;
    setSaving(true);
    const res = await fetch(`/api/jobs/${jobId}/spec`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    setSaving(false);
    if (res.ok) {
      setData((await res.json()) as JobIntake);
      toast.success("Saved — recruiter overrides stored");
    } else {
      toast.error("Save failed");
    }
  }

  // Editing helpers
  function setWeight(key: keyof JobIntake["weights"], v: number) {
    setData((d) => (d ? { ...d, weights: { ...d.weights, [key]: v } } : d));
  }
  function setChannel(key: keyof JobIntake["channels"], v: string) {
    setData((d) => (d ? { ...d, channels: { ...d.channels, [key]: v } } : d));
  }
  function setList(key: "must_have" | "nice_to_have" | "eliminatory_criteria", v: string) {
    const items = v.split(",").map((s) => s.trim()).filter(Boolean);
    setData((d) => (d ? { ...d, spec: { ...d.spec, [key]: items } } : d));
  }

  // AI-first: when opened via New-job with autorun, start the conversation from
  // the recruiter's intent (the description they just wrote). If they gave a
  // brief, the AI reacts to it; otherwise it opens by asking what they want.
  React.useEffect(() => {
    if (open && autorun && !ranRef.current && !data) {
      ranRef.current = true;
      setMode("chat");
      if (initialBrief.trim()) {
        const first: ChatMsg[] = [{ role: "user", text: initialBrief.trim() }];
        setChat(first);
        converse(first);
      } else {
        setChat([{ role: "assistant", text: "What role would you like to create? Describe it in a sentence." }]);
      }
    }
    if (!open) ranRef.current = false;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, autorun]);

  const weightTotal = data ? WEIGHT_KEYS.reduce((s, k) => s + data.weights[k], 0) : 0;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {!hideTrigger && (
        <DialogTrigger asChild>
          <Button variant="outline" size="sm" className="gap-1.5">
            <Sparkles className="size-3.5" /> Structure with AI
          </Button>
        </DialogTrigger>
      )}
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Help me with AI · {jobTitle}</DialogTitle>
          <DialogDescription>
            Give A1 a source, then review and edit before saving. Edits are stored as overrides.
          </DialogDescription>
        </DialogHeader>

        {!data && (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {(
                [
                  ["chat", "Chat with AI"],
                  ["description", "Use description"],
                  ["brief", "Paste a brief"],
                  ["upload", "Upload PDF/DOCX"],
                  ["questions", "Answer questions"],
                ] as [Mode, string][]
              ).map(([m, label]) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMode(m)}
                  className={`rounded-full px-3 py-1.5 text-xs ${mode === m ? "bg-primary text-primary-foreground" : "bg-muted"}`}
                >
                  {label}
                </button>
              ))}
            </div>

            {mode === "chat" && (
              <div className="space-y-3">
                <div className="bg-muted/40 max-h-64 space-y-2 overflow-y-auto rounded-lg p-3">
                  {chat.length === 0 && (
                    <p className="text-muted-foreground text-sm">
                      Tell the AI what role you want — it&apos;ll ask a few questions, then draft the spec.
                    </p>
                  )}
                  {chat.map((m, i) => (
                    <div key={i} className={m.role === "user" ? "text-right" : ""}>
                      <span
                        className={`inline-block rounded-2xl px-3 py-1.5 text-sm ${m.role === "user" ? "bg-primary text-primary-foreground" : "bg-background border"}`}
                      >
                        {m.text}
                      </span>
                    </div>
                  ))}
                  {chatBusy && (
                    <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
                      <Loader2 className="size-3 animate-spin" /> thinking…
                    </div>
                  )}
                </div>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    sendChat(chatInput);
                  }}
                  className="flex gap-2"
                >
                  <Input
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    placeholder={chat.length === 0 ? "e.g. I want an ML engineer with…" : "Your answer…"}
                    disabled={chatBusy}
                  />
                  <Button type="submit" disabled={chatBusy || !chatInput.trim()}>
                    Send
                  </Button>
                </form>
                {chat.some((m) => m.role === "user") && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={chatBusy || loading}
                    className="w-full"
                    onClick={() => {
                      const joined = chat.map((m) => `${m.role}: ${m.text}`).join("\n");
                      setBrief(joined);
                      setMode("brief");
                      // structure straight from the conversation
                      fetch(`/api/jobs/${jobId}/structure`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ brief: joined }),
                      })
                        .then((r) => (r.ok ? r.json() : null))
                        .then((d) => d && setData(d as JobIntake));
                    }}
                  >
                    <Sparkles className="size-3.5" /> Finalize now from this conversation
                  </Button>
                )}
              </div>
            )}
            {mode === "description" && (
              <p className="text-muted-foreground text-sm">
                A1 will structure the job&apos;s saved description.
              </p>
            )}
            {mode === "brief" && (
              <textarea
                value={brief}
                onChange={(e) => setBrief(e.target.value)}
                placeholder="Paste a rough brief or a prompt describing the role…"
                className="border-input bg-background min-h-28 w-full rounded-lg border p-3 text-sm"
              />
            )}
            {mode === "upload" && (
              <div className="grid gap-2">
                <Label htmlFor="jd-file" className="text-xs">
                  Job description file
                </Label>
                <Input id="jd-file" type="file" accept=".pdf,.docx,.txt,.md" />
              </div>
            )}
            {mode === "questions" && (
              <div className="grid gap-3">
                {questions.map((q) => (
                  <div key={q.key} className="grid gap-1">
                    <Label className="text-xs">{q.q}</Label>
                    <Input
                      value={answers[q.key] ?? ""}
                      onChange={(e) => setAnswers((a) => ({ ...a, [q.key]: e.target.value }))}
                    />
                  </div>
                ))}
              </div>
            )}

            {mode !== "chat" && (
              <Button type="button" onClick={run} disabled={loading} className="w-full">
                {loading ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
                {loading ? "Structuring…" : "Generate with AI"}
              </Button>
            )}
          </div>
        )}

        {data && (
          <div className="space-y-5 py-2 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="eyebrow mb-1">Seniority</p>
                {data.spec.seniority || "—"}
              </div>
              <div>
                <p className="eyebrow mb-1">Location</p>
                {data.spec.location || "—"}
              </div>
            </div>

            <div>
              <p className="eyebrow mb-1">Must have (comma-separated)</p>
              <Input
                defaultValue={data.spec.must_have.join(", ")}
                onBlur={(e) => setList("must_have", e.target.value)}
              />
            </div>
            <div>
              <p className="eyebrow mb-1">Eliminatory criteria — hard filters (comma-separated)</p>
              <Input
                defaultValue={data.spec.eliminatory_criteria.join(", ")}
                onBlur={(e) => setList("eliminatory_criteria", e.target.value)}
              />
            </div>

            <div>
              <div className="mb-2 flex items-center justify-between">
                <p className="eyebrow">Scoring weights</p>
                <span className={`text-xs ${weightTotal === 100 ? "text-muted-foreground" : "text-amber-600"}`}>
                  total {weightTotal}
                </span>
              </div>
              <div className="grid gap-2.5">
                {WEIGHT_KEYS.map((k) => (
                  <div key={k} className="grid grid-cols-[6rem_1fr_2.5rem] items-center gap-3">
                    <span className="text-xs capitalize">{k}</span>
                    <input
                      type="range"
                      min={0}
                      max={100}
                      value={data.weights[k]}
                      onChange={(e) => setWeight(k, Number(e.target.value))}
                    />
                    <span className="text-right text-xs tabular-nums">{data.weights[k]}</span>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <p className="eyebrow mb-2">Channel posts (editable)</p>
              <div className="grid gap-3">
                {(
                  [
                    ["linkedin_post", "LinkedIn"],
                    ["job_board_text", "Job board"],
                    ["careers_page", "Careers page"],
                    ["whatsapp_blurb", "WhatsApp"],
                  ] as [keyof JobIntake["channels"], string][]
                ).map(([key, label]) => (
                  <div key={key} className="rounded-xl border p-3">
                    <div className="mb-1.5 flex items-center justify-between">
                      <p className="text-xs font-medium">{label}</p>
                      <CopyBtn text={data.channels[key]} />
                    </div>
                    <textarea
                      value={data.channels[key]}
                      onChange={(e) => setChannel(key, e.target.value)}
                      className="border-input bg-background min-h-16 w-full rounded-md border p-2 text-xs"
                    />
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-xl border p-3">
              <div className="mb-1 flex items-center justify-between">
                <p className="text-xs font-medium">Careers tracking link</p>
                <CopyBtn text={data.tracking_link} />
              </div>
              <p className="text-muted-foreground text-xs break-all">{data.tracking_link || "—"}</p>
            </div>

            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={() => setData(null)} className="flex-1">
                Start over
              </Button>
              <Button type="button" onClick={save} disabled={saving} className="flex-1 gap-1">
                {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                Save {data.overridden ? "(overridden)" : ""}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
