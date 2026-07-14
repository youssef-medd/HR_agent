/** Small shared primitives for tidy, equal-height list rows across the dashboard. */

function initials(source: string): string {
  const parts = source
    .replace(/[^a-zA-Z ]/g, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (parts.length === 0) return "•";
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

export function Avatar({ label }: { label: string }) {
  return (
    <span className="bg-muted text-muted-foreground flex size-10 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold">
      {initials(label)}
    </span>
  );
}

const GATE_STYLE: Record<string, string> = {
  rejection: "bg-red-50 text-red-600 dark:bg-red-500/15 dark:text-red-400",
  offer: "bg-orange-50 text-primary dark:bg-orange-500/15",
  publish: "bg-blue-50 text-blue-600 dark:bg-blue-500/15 dark:text-blue-400",
};

export function GatePill({ label }: { label: string }) {
  const pretty = label.charAt(0).toUpperCase() + label.slice(1).toLowerCase();
  return (
    <span
      className={`chip ${GATE_STYLE[label.toLowerCase()] ?? "bg-muted text-muted-foreground"}`}
    >
      {pretty}
    </span>
  );
}
