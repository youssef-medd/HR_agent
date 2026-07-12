import { CheckCircle2 } from "lucide-react";

import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { type AttentionItem } from "@/lib/api/client";
import { apiGet } from "@/lib/api/server";
import { cn } from "@/lib/utils";

export const metadata = { title: "Needs attention · Welyne HR" };
export const dynamic = "force-dynamic";

function contextText(ctx: Record<string, unknown>): string {
  if (typeof ctx?.error === "string") return ctx.error;
  const keys = Object.keys(ctx ?? {});
  return keys.length ? JSON.stringify(ctx) : "Awaiting a recruiter decision.";
}

export default async function AttentionPage() {
  const items = await apiGet<AttentionItem[]>("/needs-attention", []);
  const open = items.filter((a) => a.status === "open");
  const resolved = items.filter((a) => a.status !== "open");

  return (
    <>
      <PageHeader
        eyebrow="Human gates"
        title="Needs attention"
        description="No rejection, offer or publication leaves the system without a decision recorded here. Every resolution is written to the audit log."
      />

      <section className="mb-12">
        <p className="eyebrow eyebrow-accent mb-4">Open · {open.length}</p>
        {open.length === 0 ? (
          <div className="text-muted-foreground border border-dashed px-6 py-12 text-center text-sm">
            Nothing waiting on a human right now.
          </div>
        ) : (
          <div className="space-y-px border bg-border">
            {open.map((item) => (
              <article key={item.id} className="bg-card p-5">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="font-medium">
                      {item.full_name || item.candidate_ref || `Application #${item.application_id}`}
                    </span>
                  </div>
                  <span
                    className={cn(
                      "font-mono border px-2 py-0.5 text-[10px] tracking-[0.08em] uppercase",
                      item.gate
                        ? "text-destructive border-destructive/40"
                        : "text-muted-foreground border-border",
                    )}
                  >
                    {item.gate ? `gate · ${item.gate}` : item.reason.replaceAll("_", " ")}
                  </span>
                </div>
                <p className="text-muted-foreground mb-4 max-w-2xl text-sm leading-relaxed">
                  {contextText(item.context)}
                </p>
                <div className="flex items-center justify-between">
                  <p className="text-muted-foreground font-mono text-[10px]">
                    app #{item.application_id} ·{" "}
                    {new Date(item.created_at).toLocaleString("en-GB", {
                      dateStyle: "medium",
                      timeStyle: "short",
                    })}
                  </p>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" disabled>
                      Review
                    </Button>
                    <Button size="sm" disabled>
                      {item.gate === "offer"
                        ? "Approve offer"
                        : item.gate === "rejection"
                          ? "Approve rejection"
                          : "Resolve"}
                    </Button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
        <p className="text-muted-foreground mt-3 text-xs">
          Actions are disabled — resolution endpoints land with the orchestrator API in sprint 3.
        </p>
      </section>

      <section>
        <p className="eyebrow mb-4">Resolved · {resolved.length}</p>
        {resolved.length === 0 ? (
          <p className="text-muted-foreground text-xs">No resolved items yet.</p>
        ) : (
          <div className="space-y-px border bg-border">
            {resolved.map((item) => (
              <article
                key={item.id}
                className="bg-card flex items-start gap-3 p-5 opacity-70"
              >
                <CheckCircle2 className="text-primary mt-0.5 size-4 shrink-0" aria-hidden />
                <div>
                  <p className="text-sm font-medium">
                    {item.full_name || item.candidate_ref || `Application #${item.application_id}`}
                    <span className="text-muted-foreground"> · {item.gate ?? item.reason}</span>
                  </p>
                  <p className="text-muted-foreground mt-1 text-sm">
                    {contextText(item.context)}
                  </p>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
