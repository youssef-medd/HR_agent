"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

/** What the approve button does, per gate. Anything unlisted is a plain resolve. */
const APPROVE_LABEL: Record<string, string> = {
  offer: "Approve offer",
  rejection: "Approve rejection",
  interview_invite: "Invite to interview",
};

function APPROVED_TOAST(gate: string | null, candidate: string): string {
  if (gate === "interview_invite") return `${candidate} invited — they can now pick a time`;
  if (gate === "offer") return `Offer approved for ${candidate}`;
  if (gate === "rejection") return `Rejection approved for ${candidate}`;
  return `Resolved for ${candidate}`;
}

function DECLINED_TOAST(gate: string | null, candidate: string): string {
  if (gate === "interview_invite") return `${candidate} not invited — no slots were sent`;
  return `${candidate} kept — ${gate ?? "item"} not approved`;
}

/** Approve / keep buttons for an open human gate. Posts the decision and refreshes. */
export function GateActions({
  itemId,
  gate,
  candidate,
}: {
  itemId: number;
  gate: string | null;
  candidate: string;
}) {
  const router = useRouter();
  const [pending, setPending] = React.useState<"approve" | "reject" | null>(null);

  async function decide(decision: "approve" | "reject") {
    if (pending) return;
    setPending(decision);

    const res = await fetch(`/api/attention/${itemId}/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    });
    setPending(null);

    if (!res.ok) {
      const err = await res.json().catch(() => null);
      toast.error(err?.detail ?? err?.error ?? `Failed (${res.status})`);
      return;
    }

    toast.success(
      decision === "approve" ? APPROVED_TOAST(gate, candidate) : DECLINED_TOAST(gate, candidate),
    );
    router.refresh();
  }

  const approveLabel = APPROVE_LABEL[gate ?? ""] ?? "Resolve";
  const rejectLabel = gate === "interview_invite" ? "Not this time" : "Keep candidate";

  return (
    <div className="flex gap-2">
      <Button
        variant="outline"
        size="sm"
        disabled={pending !== null}
        onClick={() => decide("reject")}
      >
        {pending === "reject" && <Loader2 className="size-3.5 animate-spin" />}
        {rejectLabel}
      </Button>
      <Button size="sm" disabled={pending !== null} onClick={() => decide("approve")}>
        {pending === "approve" && <Loader2 className="size-3.5 animate-spin" />}
        {approveLabel}
      </Button>
    </div>
  );
}
