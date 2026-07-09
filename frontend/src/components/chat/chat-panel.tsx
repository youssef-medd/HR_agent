"use client";

import * as React from "react";
import { Loader2, SendHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface Exchange {
  prompt: string;
  reply: string;
}

export function ChatPanel() {
  const [prompt, setPrompt] = React.useState("");
  const [history, setHistory] = React.useState<Exchange[]>([]);
  const [pending, setPending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function send() {
    const trimmed = prompt.trim();
    if (!trimmed || pending) return;

    setPending(true);
    setError(null);

    const res = await fetch("/api/chat/hello", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: trimmed }),
    });

    setPending(false);

    if (!res.ok) {
      const data = await res.json().catch(() => null);
      setError(data?.error ?? `Request failed (${res.status})`);
      return;
    }

    const data = (await res.json()) as { reply: string };
    setHistory((h) => [...h, { prompt: trimmed, reply: data.reply }]);
    setPrompt("");
  }

  return (
    <div className="max-w-2xl">
      <div className="mb-6 space-y-px border bg-border empty:hidden">
        {history.map((ex, i) => (
          <div key={i} className="bg-card space-y-3 p-5">
            <div>
              <p className="eyebrow mb-1.5">Prompt</p>
              <p className="text-sm">{ex.prompt}</p>
            </div>
            <div>
              <p className="eyebrow eyebrow-accent mb-1.5">Reply</p>
              <p className="text-sm leading-relaxed whitespace-pre-wrap">
                {ex.reply}
              </p>
            </div>
          </div>
        ))}
      </div>

      {error && (
        <p role="alert" className="text-destructive mb-4 text-sm">
          {error}
        </p>
      )}

      <div className="flex items-end gap-2">
        <Textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder="Say hello to the LLM gateway…"
          maxLength={2000}
          rows={2}
          className="resize-none"
          aria-label="Prompt"
        />
        <Button onClick={send} disabled={pending || !prompt.trim()} size="icon">
          {pending ? (
            <Loader2 className="animate-spin" aria-hidden />
          ) : (
            <SendHorizontal aria-hidden />
          )}
          <span className="sr-only">Send</span>
        </Button>
      </div>
    </div>
  );
}
