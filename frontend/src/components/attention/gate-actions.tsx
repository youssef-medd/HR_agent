"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

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
      decision === "approve"
        ? `${gate === "offer" ? "Offer" : "Rejection"} approved for ${candidate}`
        : `${candidate} kept — ${gate ?? "item"} not approved`,
    );
    router.refresh();
  }

  const approveLabel =
    gate === "offer" ? "Approve offer" : gate === "rejection" ? "Approve rejection" : "Resolve";

  return (
    <div className="flex gap-2">
      <Button
        variant="outline"
        size="sm"
        disabled={pending !== null}
        onClick={() => decide("reject")}
      >
        {pending === "reject" && <Loader2 className="size-3.5 animate-spin" />}
        Keep candidate
      </Button>
      <Button size="sm" disabled={pending !== null} onClick={() => decide("approve")}>
        {pending === "approve" && <Loader2 className="size-3.5 animate-spin" />}
        {approveLabel}
      </Button>
    </div>
  );
}
