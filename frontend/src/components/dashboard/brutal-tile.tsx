"use client";

/**
 * Entrance/hover motion for the brutalist dashboard tiles.
 *
 * Exists purely so `app/(app)/page.tsx` can stay a server component: it fetches
 * with `apiGet`, and framer-motion needs the client. Tiles stagger in on load
 * and lift toward their offset shadow on hover.
 *
 * `prefers-reduced-motion` gets the finished state immediately with no
 * animation — the hard-shadow look survives, the movement doesn't.
 */

import * as React from "react";
import { motion, useReducedMotion } from "framer-motion";

import { cn } from "@/lib/utils";

export function BrutalTile({
  children,
  className,
  index = 0,
  lift = true,
}: {
  children: React.ReactNode;
  className?: string;
  /** Position in the stagger sequence. */
  index?: number;
  /** Set false for tiles that hold their own interactive rows. */
  lift?: boolean;
}) {
  const reduced = useReducedMotion();

  return (
    <motion.div
      initial={reduced ? false : { opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={
        reduced
          ? { duration: 0 }
          : { type: "spring", stiffness: 220, damping: 24, delay: index * 0.06 }
      }
      className={cn(lift && "brutal-lift", className)}
    >
      {children}
    </motion.div>
  );
}

/**
 * Counts up to `value` on mount — a small piece of life on an otherwise static
 * figure. Skipped entirely under reduced motion.
 */
export function BrutalCounter({ value }: { value: number }) {
  const reduced = useReducedMotion();
  const [shown, setShown] = React.useState(reduced ? value : 0);

  React.useEffect(() => {
    if (reduced || value === 0) {
      setShown(value);
      return;
    }
    const DURATION = 550;
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / DURATION);
      // easeOutCubic — fast start, settles onto the real number
      setShown(Math.round(value * (1 - Math.pow(1 - t, 3))));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value, reduced]);

  return <>{shown}</>;
}
