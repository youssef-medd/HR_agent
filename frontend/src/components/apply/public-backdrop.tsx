"use client";

/**
 * The cinematic dot-matrix backdrop, carried over from the login.
 *
 * `fixed` rather than `absolute`: the candidate pages scroll, and the effect
 * should stay behind the content the whole way down instead of scrolling off.
 * Honours prefers-reduced-motion with the same static gradient the login falls
 * back to — the canvas runs a shader loop, which is exactly what someone with
 * that preference set is asking not to see.
 */

import * as React from "react";

import { CanvasRevealEffect } from "@/components/ui/canvas-reveal";

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = React.useState(false);
  React.useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

export function PublicBackdrop() {
  const reducedMotion = usePrefersReducedMotion();

  if (reducedMotion) {
    return (
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 z-0"
        style={{
          background:
            "radial-gradient(90% 70% at 50% 100%, rgba(255,107,0,0.18) 0%, transparent 60%), #000",
        }}
      />
    );
  }

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 z-0">
      <CanvasRevealEffect
        animationSpeed={3}
        containerClassName="bg-black"
        colors={[
          [255, 107, 0],
          [255, 170, 80],
        ]}
        dotSize={6}
        reverse={false}
      />
      {/* Softens the dots behind the header, as on the login. */}
      <div className="absolute inset-x-0 top-0 h-1/3 bg-gradient-to-b from-black to-transparent" />
      {/* Keeps long-form content readable where the field is densest. */}
      <div className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black via-black/60 to-transparent" />
    </div>
  );
}
