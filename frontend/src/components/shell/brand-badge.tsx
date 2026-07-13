import { Sparkle, UserRound } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * "Intelligent HR" brand badge — orange-outlined pill with a person icon and a
 * sparkle perched on the top-right border. `tone` picks ink for light or dark
 * surroundings (the cinematic login sits on black regardless of theme).
 */
export function BrandBadge({
  tone = "light",
  className,
}: {
  tone?: "light" | "dark";
  className?: string;
}) {
  return (
    <span
      className={cn(
        "border-primary/70 relative inline-flex items-center gap-1.5 rounded-full border px-3 py-1",
        className,
      )}
    >
      <UserRound className="text-primary size-3.5" strokeWidth={2.25} aria-hidden />
      <span
        className={cn(
          "text-xs font-semibold tracking-tight whitespace-nowrap",
          tone === "dark" ? "text-white" : "text-foreground",
        )}
      >
        Intelligent HR
      </span>
      <Sparkle
        className="text-primary fill-primary absolute -top-2 -right-1.5 size-3.5"
        aria-hidden
      />
      <span
        className="bg-primary absolute -top-0.5 -right-2.5 size-1 rounded-full"
        aria-hidden
      />
    </span>
  );
}
