import { cn } from "@/lib/utils";
import type { ApplicationState } from "@/lib/mocks/types";

const STATE_STYLES: Record<string, string> = {
  RECEIVED: "text-muted-foreground border-border",
  PARSED: "text-muted-foreground border-border",
  SCORED: "text-foreground border-border",
  SHORTLISTED: "text-primary border-primary/40",
  POOL: "text-muted-foreground border-border",
  DECLINE_PENDING: "text-destructive border-destructive/40",
  PRESCREENING: "text-foreground border-border",
  PRESCREENED: "text-foreground border-border",
  INTERVIEW_SCHEDULED: "text-primary border-primary/40",
  INTERVIEWED: "text-foreground border-border",
  OFFER: "text-primary border-primary/40",
  HIRED: "text-primary border-primary/40",
  ONBOARDING: "text-foreground border-border",
  DECLINED: "text-muted-foreground border-border",
  NEEDS_ATTENTION: "text-destructive border-destructive/40",
};

export function StateBadge({ state }: { state: ApplicationState }) {
  return (
    <span
      className={cn(
        "font-mono inline-flex items-center border px-2 py-0.5 text-[10px] font-medium tracking-[0.08em] whitespace-nowrap uppercase",
        STATE_STYLES[state] ?? "text-muted-foreground border-border"
      )}
    >
      {state.replaceAll("_", " ")}
    </span>
  );
}
