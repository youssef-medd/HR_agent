"use client";

import * as React from "react";
import { CheckCircle2, Loader2, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { PrescreenView } from "@/lib/api/client";

export function PrescreenChat({ email, appId }: { email: string; appId: number }) {
  const [view, setView] = React.useState<PrescreenView | null>(null);
  const [input, setInput] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const endRef = React.useRef<HTMLDivElement>(null);

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

  async function send() {
    const msg = input.trim();
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
  }

  return (
    <div className="surface flex h-[26rem] flex-col p-0">
      <div className="border-b px-5 py-3">
        <p className="font-heading text-sm font-semibold">Pre-screening chat</p>
        <p className="text-muted-foreground text-xs">
          Our AI assistant asks a few quick questions. A human makes the final decision.
        </p>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
        {(view?.transcript ?? []).map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div
              className={
                m.role === "user"
                  ? "bg-primary max-w-[80%] rounded-2xl rounded-br-sm px-3.5 py-2 text-sm text-white"
                  : "bg-muted max-w-[80%] rounded-2xl rounded-bl-sm px-3.5 py-2 text-sm"
              }
            >
              {m.text}
            </div>
          </div>
        ))}
        {view?.done && (
          <div className="text-muted-foreground flex items-center justify-center gap-1.5 pt-2 text-xs">
            <CheckCircle2 className="size-4 text-emerald-500" /> Pre-screening complete
          </div>
        )}
        <div ref={endRef} />
      </div>

      {!view?.done && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send();
          }}
          className="flex items-center gap-2 border-t px-4 py-3"
        >
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={view?.awaiting ? "Type your answer…" : "Waiting for the assistant…"}
            disabled={sending}
          />
          <Button type="submit" size="icon" disabled={sending || !input.trim()}>
            {sending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
          </Button>
        </form>
      )}
    </div>
  );
}
