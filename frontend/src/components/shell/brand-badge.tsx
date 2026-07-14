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
        "border-primary/60 relative inline-flex items-center gap-2 rounded-full border bg-transparent px-4 py-1.5",
        className,
      )}
    >
      <UserRound className="text-primary size-4" strokeWidth={2} aria-hidden />
      <span
        className={cn(
          "font-heading text-sm font-semibold tracking-tight whitespace-nowrap",
          tone === "dark" ? "text-white" : "text-foreground",
        )}
      >
        Intelligent HR
      </span>
      <Sparkle
        className="text-primary fill-primary absolute -top-2.5 -right-2 size-4"
        aria-hidden
      />
      <span
        className="bg-primary absolute -top-0.5 -right-3 size-1 rounded-full"
        aria-hidden
      />
    </span>
  );
}
