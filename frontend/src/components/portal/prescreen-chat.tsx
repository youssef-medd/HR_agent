"use client";

import * as React from "react";
import { Check, CheckCircle2, Loader2, Send, Sparkles } from "lucide-react";

import type { PrescreenView } from "@/lib/api/client";

/** Consent is the one turn with exactly two valid answers — offer them as chips. */
const CONSENT_REPLIES = ["YES", "NO"] as const;

export function PrescreenChat({ email, appId }: { email: string; appId: number }) {
  const [view, setView] = React.useState<PrescreenView | null>(null);
  const [input, setInput] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const endRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const load = React.useCallback(async () => {
    const res = await fetch(
      `/api/public/prescreen?email=${encodeURIComponent(email)}&application_id=${appId}`,
      { cache: "no-store" },
    );
    if (res.ok) setView((await res.json()) as PrescreenView);
  }, [email, appId]);

  React.useEffect(() => {
    load();
    const t = setInterval(load, 2000); // catch the assistant's next question
    return () => clearInterval(t);
  }, [load]);

  React.useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [view?.transcript.length]);

  const send = React.useCallback(
    async (raw: string) => {
      const msg = raw.trim();
      if (!msg || sending) return;
      setSending(true);
      setInput("");
      // optimistic: show the user message immediately
      setView((v) =>
        v ? { ...v, transcript: [...v.transcript, { role: "user", text: msg }], awaiting: false } : v,
      );
      await fetch("/api/public/prescreen/reply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, application_id: appId, message: msg }),
      });
      setSending(false);
      setTimeout(load, 800);
      inputRef.current?.focus();
    },
    [appId, email, load, sending],
  );

  const transcript = view?.transcript ?? [];
  const answered = transcript.filter((m) => m.role === "user").length;
  const consentTurn = view?.status === "awaiting_consent" && transcript.length > 0;
  // The assistant holds the turn: we have replied and its next question is in flight.
  const composing = !view?.done && !view?.awaiting && transcript.length > 0;

  return (
    <div className="flex h-[30rem] flex-col overflow-hidden rounded-3xl border border-white/[0.08] bg-black/55 shadow-[0_8px_40px_rgba(0,0,0,0.5)] backdrop-blur-xl">
      {/* Header ------------------------------------------------------------ */}
      <div className="relative flex items-center gap-3 border-b border-white/[0.08] px-5 py-3.5">
        <span className="relative flex size-9 shrink-0 items-center justify-center">
          <span className="bg-primary/25 agent-pulse absolute inset-0 rounded-full blur-[6px]" />
          <span className="from-primary relative flex size-9 items-center justify-center rounded-full bg-gradient-to-br to-[#ff9a4d] text-white shadow-[0_2px_12px_rgba(226,97,26,0.45)]">
            <Sparkles className="size-4" aria-hidden />
          </span>
        </span>

        <div className="min-w-0 flex-1">
          <p className="font-heading text-sm font-semibold text-white">Pre-screening chat</p>
          <p className="truncate text-xs text-white/45">
            Our AI assistant asks a few quick questions. A human makes the final decision.
          </p>
        </div>

        <span
          className={`flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-medium tracking-wide uppercase ${
            view?.done
              ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
              : "border-white/10 bg-white/[0.04] text-white/55"
          }`}
        >
          <span
            className={`size-1.5 rounded-full ${view?.done ? "bg-emerald-400" : "bg-primary"}`}
            aria-hidden
          />
          {view?.done ? "Complete" : answered > 0 ? `${answered} answered` : "Online"}
        </span>
      </div>

      {/* Transcript -------------------------------------------------------- */}
      <div className="chat-scroll relative flex-1 space-y-3 overflow-y-auto px-5 py-4">
        {transcript.map((m, i) => (
          <div
            key={i}
            className={`msg-in flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={
                m.role === "user"
                  ? "from-primary max-w-[82%] rounded-2xl rounded-br-md bg-gradient-to-br to-[#f0803c] px-3.5 py-2.5 text-sm leading-relaxed text-white shadow-[0_4px_16px_-6px_rgba(226,97,26,0.7)]"
                  : "max-w-[82%] rounded-2xl rounded-bl-md border border-white/[0.09] bg-white/[0.055] px-3.5 py-2.5 text-sm leading-relaxed text-white/85 shadow-[0_2px_10px_-6px_rgba(0,0,0,0.8)]"
              }
            >
              {m.text}
            </div>
          </div>
        ))}

        {composing && (
          <div className="msg-in flex justify-start" aria-live="polite">
            <div className="flex items-center gap-1.5 rounded-2xl rounded-bl-md border border-white/[0.09] bg-white/[0.055] px-4 py-3">
              <span className="sr-only">The assistant is typing</span>
              {[0, 1, 2].map((d) => (
                <span key={d} className="typing-dot size-1.5 rounded-full bg-white/70" aria-hidden />
              ))}
            </div>
          </div>
        )}

        {view?.done && (
          <div className="msg-in flex flex-col items-center gap-1 pt-3 text-center">
            <CheckCircle2 className="size-6 text-emerald-400" aria-hidden />
            <p className="text-sm font-medium text-white/85">Pre-screening complete</p>
            <p className="text-xs text-white/40">
              Thanks — your answers are with the recruiting team.
            </p>
          </div>
        )}

        <div ref={endRef} />
      </div>

      {/* Composer ---------------------------------------------------------- */}
      {!view?.done && (
        <div className="border-t border-white/[0.08] bg-white/[0.02] px-4 py-3">
          {consentTurn && (
            <div className="mb-2.5 flex gap-2">
              {CONSENT_REPLIES.map((reply) => (
                <button
                  key={reply}
                  type="button"
                  disabled={sending}
                  onClick={() => send(reply)}
                  className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${
                    reply === "YES"
                      ? "border-primary/40 bg-primary/12 text-primary hover:bg-primary/20"
                      : "border-white/12 bg-white/[0.04] text-white/60 hover:border-white/25 hover:text-white/85"
                  }`}
                >
                  {reply === "YES" && <Check className="size-3" aria-hidden />}
                  {reply === "YES" ? "Yes, continue" : "No, thanks"}
                </button>
              ))}
            </div>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="flex items-center gap-2"
          >
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={view?.awaiting ? "Type your answer…" : "Waiting for the assistant…"}
              disabled={sending}
              aria-label="Your answer"
              className="focus:border-primary/60 focus:ring-primary/15 w-full rounded-full border border-white/10 bg-white/[0.04] px-4 py-2.5 text-sm text-white transition-all placeholder:text-white/25 focus:ring-4 focus:outline-none disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={sending || !input.trim()}
              aria-label="Send"
              className="from-primary flex size-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br to-[#f0803c] text-white shadow-[0_4px_14px_-4px_rgba(226,97,26,0.8)] transition-all hover:brightness-110 disabled:opacity-35 disabled:shadow-none"
            >
              {sending ? (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              ) : (
                <Send className="size-4" aria-hidden />
              )}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
