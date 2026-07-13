import { CheckCircle2 } from "lucide-react";

import { GateActions } from "@/components/attention/gate-actions";
import { Avatar, GatePill } from "@/components/shell/row-bits";
import { PageHeader } from "@/components/shell/page-header";
import { type AttentionItem } from "@/lib/api/client";
import { apiGet } from "@/lib/api/server";

export const metadata = { title: "Needs attention · Welyne HR" };
export const dynamic = "force-dynamic";

function contextText(ctx: Record<string, unknown>): string {
  if (typeof ctx?.error === "string") return ctx.error;
  const keys = Object.keys(ctx ?? {});
  return keys.length ? JSON.stringify(ctx) : "Awaiting a recruiter decision.";
}

function nameOf(item: AttentionItem): string {
  return item.full_name || item.candidate_ref || `Application #${item.application_id}`;
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
        <div className="mb-3 flex items-center gap-2">
          <p className="eyebrow eyebrow-accent">Open</p>
          <span className="bg-muted text-muted-foreground font-mono flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[10px]">
            {open.length}
          </span>
        </div>

        {open.length === 0 ? (
          <div className="surface text-muted-foreground px-6 py-12 text-center text-sm">
            Nothing waiting on a human right now.
          </div>
        ) : (
          <div className="surface space-y-1.5 p-3">
            {open.map((item) => (
              <article
                key={item.id}
                className="hover:bg-accent flex flex-wrap items-center gap-x-4 gap-y-3 rounded-2xl p-3 transition-colors duration-200"
              >
                <Avatar label={nameOf(item)} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-sm font-medium">{nameOf(item)}</p>
                    <GatePill label={item.gate ?? item.reason.replaceAll("_", " ")} />
                  </div>
                  <p className="text-muted-foreground mt-1 line-clamp-1 text-xs">
                    {contextText(item.context)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <p className="text-muted-foreground font-mono hidden text-[10px] sm:block">
                    app #{item.application_id} ·{" "}
                    {new Date(item.created_at).toLocaleDateString("en-GB", { dateStyle: "medium" })}
                  </p>
                  <GateActions
                    itemId={item.id}
                    gate={item.gate}
                    candidate={nameOf(item)}
                  />
                </div>
              </article>
            ))}
          </div>
        )}
        <p className="text-muted-foreground mt-3 text-xs">
          Every decision is recorded with the recruiter&apos;s identity and written to the audit log.
        </p>
      </section>

      <section>
        <div className="mb-3 flex items-center gap-2">
          <p className="eyebrow">Resolved</p>
          <span className="bg-muted text-muted-foreground font-mono flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[10px]">
            {resolved.length}
          </span>
        </div>
        {resolved.length === 0 ? (
          <p className="text-muted-foreground text-xs">No resolved items yet.</p>
        ) : (
          <div className="surface space-y-1.5 p-3">
            {resolved.map((item) => (
              <article
                key={item.id}
                className="flex items-center gap-3 rounded-2xl p-3 opacity-80"
              >
                <CheckCircle2 className="text-primary size-4 shrink-0" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {nameOf(item)}
                    <span className="text-muted-foreground"> · {item.gate ?? item.reason}</span>
                  </p>
                  <p className="text-muted-foreground mt-0.5 line-clamp-1 text-xs">
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
