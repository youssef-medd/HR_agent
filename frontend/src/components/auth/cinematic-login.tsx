"use client";

/**
 * Cinematic Welyne entry.
 *
 * Steps: role select (Recruiter / Candidate) → real email+password sign-in
 * (BFF /api/auth/login) → reverse-canvas outro → dashboard. The candidate
 * branch shows a "portal coming soon" panel — candidate self-service lands in
 * a later phase of the roadmap.
 */

import * as React from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, BriefcaseBusiness, Loader2, UserRound } from "lucide-react";

import { BrandBadge } from "@/components/shell/brand-badge";
import { CanvasRevealEffect } from "@/components/ui/canvas-reveal";

type Step = "role" | "signin" | "candidate" | "success";

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

const glassInput =
  "w-full backdrop-blur-[1px] bg-white/5 text-white border border-white/10 rounded-full py-3 px-5 focus:outline-none focus:border-white/40 placeholder:text-white/30 transition-colors duration-200";

export function CinematicLogin() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const reducedMotion = usePrefersReducedMotion();

  const [step, setStep] = React.useState<Step>("role");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);
  const [initialCanvasVisible, setInitialCanvasVisible] = React.useState(true);
  const [reverseCanvasVisible, setReverseCanvasVisible] = React.useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending) return;
    setError(null);
    setPending(true);

    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    setPending(false);

    if (!res.ok) {
      const data = await res.json().catch(() => null);
      setError(data?.error ?? "Sign-in failed. Try again.");
      return;
    }

    // Cinematic outro: collapse the dots, then enter the console.
    setReverseCanvasVisible(true);
    setTimeout(() => setInitialCanvasVisible(false), 50);
    setStep("success");

    const next = searchParams.get("next");
    const target = next && next.startsWith("/") ? next : "/";
    setTimeout(
      () => {
        router.replace(target);
        router.refresh();
      },
      reducedMotion ? 200 : 1600,
    );
  }

  return (
    <div className="relative flex min-h-svh w-full flex-col bg-black">
      {/* Backdrop */}
      <div className="absolute inset-0 z-0">
        {reducedMotion ? (
          <div
            className="absolute inset-0"
            style={{
              background:
                "radial-gradient(90% 70% at 50% 100%, rgba(255,107,0,0.18) 0%, transparent 60%), #000",
            }}
          />
        ) : (
          <>
            {initialCanvasVisible && (
              <div className="absolute inset-0">
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
              </div>
            )}
            {reverseCanvasVisible && (
              <div className="absolute inset-0">
                <CanvasRevealEffect
                  animationSpeed={4}
                  containerClassName="bg-black"
                  colors={[
                    [255, 107, 0],
                    [255, 170, 80],
                  ]}
                  dotSize={6}
                  reverse={true}
                />
              </div>
            )}
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_rgba(0,0,0,1)_0%,_transparent_100%)]" />
            <div className="absolute top-0 right-0 left-0 h-1/3 bg-gradient-to-b from-black to-transparent" />
          </>
        )}
      </div>

      {/* Floating mini navbar */}
      <header className="fixed top-6 left-1/2 z-20 flex w-[calc(100%-2rem)] -translate-x-1/2 items-center justify-between rounded-full border border-white/10 bg-white/5 px-5 py-2.5 backdrop-blur-sm sm:w-auto sm:gap-10">
        <div className="flex items-center gap-2.5">
          <Image src="/logo.png" alt="Welyne" width={26} height={26} />
          <span className="font-heading text-sm font-semibold tracking-tight text-white">
            welyne
          </span>
          <span className="h-4 w-px bg-white/15" aria-hidden />
          <BrandBadge tone="dark" className="hidden sm:inline-flex" />
        </div>
        <a
          href="https://welyne.com"
          target="_blank"
          rel="noreferrer"
          className="text-xs text-white/50 transition-colors duration-200 hover:text-white"
        >
          welyne.com
        </a>
      </header>

      {/* Content */}
      <div className="relative z-10 flex flex-1 items-center justify-center px-6">
        <div className={step === "role" ? "w-full max-w-lg" : "w-full max-w-md"}>
          <AnimatePresence mode="wait">
            {step === "role" && (
              <motion.div
                key="role"
                initial={{ opacity: 0, y: 40 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -40 }}
                transition={{ duration: 0.35, ease: "easeOut" }}
                className="space-y-8 text-center"
              >
                <div className="space-y-2">
                  <h1 className="text-4xl leading-[1.1] font-bold tracking-tight text-white">
                    HR, reinvented
                    <br />
                    by AI agents
                  </h1>
                  <p className="text-lg font-light text-white/60">
                    Who is signing in?
                  </p>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  {/* Recruiter — the primary path */}
                  <button
                    onClick={() => setStep("signin")}
                    className="group relative flex flex-col items-center gap-4 overflow-hidden rounded-3xl p-[1px] text-center transition-transform duration-200 hover:-translate-y-1"
                  >
                    {/* gradient ring */}
                    <span
                      aria-hidden
                      className="absolute inset-0 rounded-3xl bg-gradient-to-b from-[#ff8a33] via-[#ff6b00]/45 to-transparent opacity-80 transition-opacity duration-200 group-hover:opacity-100"
                    />
                    <span className="relative flex w-full flex-col items-center gap-4 rounded-[calc(1.5rem-1px)] bg-[#141210] px-6 pt-8 pb-6">
                      {/* halo */}
                      <span
                        aria-hidden
                        className="pointer-events-none absolute -top-10 left-1/2 h-28 w-40 -translate-x-1/2 rounded-full bg-[#ff6b00]/25 blur-2xl transition-opacity duration-300 group-hover:opacity-100 sm:opacity-60"
                      />
                      <span className="relative flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br from-[#ff8a33] to-[#e85d00] shadow-[0_6px_20px_rgba(255,107,0,0.35)]">
                        <BriefcaseBusiness className="size-5 text-white" aria-hidden />
                      </span>
                      <span className="relative">
                        <span className="block text-lg font-semibold tracking-tight text-white">
                          Recruiter
                        </span>
                        <span className="mt-1 block text-[13px] leading-relaxed text-white/45">
                          Jobs, candidates and human gates
                        </span>
                      </span>
                      <span className="text-primary relative inline-flex items-center gap-1.5 text-sm font-medium">
                        Sign in
                        <ArrowRight
                          className="size-3.5 transition-transform duration-200 group-hover:translate-x-1"
                          aria-hidden
                        />
                      </span>
                    </span>
                  </button>

                  {/* Candidate — quiet secondary path */}
                  <button
                    onClick={() => setStep("candidate")}
                    className="group relative flex flex-col items-center gap-4 rounded-3xl border border-white/[0.08] bg-white/[0.03] px-6 pt-8 pb-6 text-center backdrop-blur-[2px] transition-all duration-200 hover:-translate-y-1 hover:border-white/20 hover:bg-white/[0.06]"
                  >
                    <span className="flex size-12 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.06] transition-colors duration-200 group-hover:border-white/20">
                      <UserRound className="size-5 text-white/80" aria-hidden />
                    </span>
                    <span>
                      <span className="block text-lg font-semibold tracking-tight text-white">
                        Candidate
                      </span>
                      <span className="mt-1 block text-[13px] leading-relaxed text-white/45">
                        Track your application journey
                      </span>
                    </span>
                    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-white/50 transition-colors duration-200 group-hover:text-white">
                      Explore
                      <ArrowRight
                        className="size-3.5 transition-transform duration-200 group-hover:translate-x-1"
                        aria-hidden
                      />
                    </span>
                  </button>
                </div>
              </motion.div>
            )}

            {step === "signin" && (
              <motion.div
                key="signin"
                initial={{ opacity: 0, x: 80 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -80 }}
                transition={{ duration: 0.35, ease: "easeOut" }}
                className="space-y-6 text-center"
              >
                <div className="space-y-1">
                  <h1 className="text-4xl font-bold tracking-tight text-white">
                    Welcome back
                  </h1>
                  <p className="text-lg font-light text-white/60">
                    Sign in to the recruitment console
                  </p>
                </div>

                <form onSubmit={onSubmit} className="space-y-3">
                  <input
                    type="email"
                    autoComplete="email"
                    placeholder="you@welyne.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className={glassInput}
                    required
                  />
                  <input
                    type="password"
                    autoComplete="current-password"
                    placeholder="Password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className={glassInput}
                    required
                  />

                  {error && (
                    <p role="alert" className="text-sm text-red-400">
                      {error}
                    </p>
                  )}

                  <div className="flex gap-3 pt-2">
                    <button
                      type="button"
                      onClick={() => {
                        setStep("role");
                        setError(null);
                      }}
                      className="w-[30%] rounded-full border border-white/10 bg-white/5 py-3 font-medium text-white/70 transition-colors duration-200 hover:bg-white/10 hover:text-white"
                    >
                      Back
                    </button>
                    <button
                      type="submit"
                      disabled={pending}
                      className="bg-primary flex flex-1 items-center justify-center gap-2 rounded-full py-3 font-semibold text-white transition-colors duration-200 hover:bg-[#f05e00] disabled:opacity-60"
                    >
                      {pending && <Loader2 className="size-4 animate-spin" aria-hidden />}
                      {pending ? "Signing in…" : "Sign in"}
                    </button>
                  </div>
                </form>

                <p className="pt-6 text-xs text-white/40">
                  Access is restricted to Welyne recruitment staff. Sessions expire after 8
                  hours.
                </p>
              </motion.div>
            )}

            {step === "candidate" && (
              <motion.div
                key="candidate"
                initial={{ opacity: 0, x: 80 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -80 }}
                transition={{ duration: 0.35, ease: "easeOut" }}
                className="space-y-6 text-center"
              >
                <div className="space-y-1">
                  <h1 className="text-4xl font-bold tracking-tight text-white">
                    Candidate portal
                  </h1>
                  <p className="text-lg font-light text-white/60">
                    Apply to a role or track your application
                  </p>
                </div>

                <div className="space-y-3">
                  <Link
                    href="/apply"
                    className="bg-primary hover:bg-primary/90 block w-full rounded-full py-3 font-medium text-white transition-colors duration-200"
                  >
                    Browse open roles &amp; apply
                  </Link>
                  <Link
                    href="/portal"
                    className="block w-full rounded-full border border-white/15 bg-white/5 py-3 font-medium text-white/80 transition-colors duration-200 hover:bg-white/10 hover:text-white"
                  >
                    Track my application
                  </Link>
                </div>

                <p className="text-xs leading-relaxed text-white/40">
                  Web chat pre-screening and interview booking are coming here soon. Questions?
                  Reach the team at{" "}
                  <Link
                    href="https://welyne.com"
                    target="_blank"
                    className="text-white/70 underline decoration-white/30 transition-colors hover:decoration-white"
                  >
                    welyne.com
                  </Link>
                  .
                </p>

                <button
                  onClick={() => setStep("role")}
                  className="w-full rounded-full border border-white/10 bg-white/5 py-3 font-medium text-white/70 transition-colors duration-200 hover:bg-white/10 hover:text-white"
                >
                  Back
                </button>
              </motion.div>
            )}

            {step === "success" && (
              <motion.div
                key="success"
                initial={{ opacity: 0, y: 40 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, ease: "easeOut", delay: 0.2 }}
                className="space-y-6 text-center"
              >
                <div className="space-y-1">
                  <h1 className="text-4xl font-bold tracking-tight text-white">
                    You&apos;re in
                  </h1>
                  <p className="text-lg font-light text-white/60">
                    Opening the console…
                  </p>
                </div>
                <motion.div
                  initial={{ scale: 0.8, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ duration: 0.4, delay: 0.4 }}
                  className="py-6"
                >
                  <span className="bg-primary mx-auto flex size-16 items-center justify-center rounded-full">
                    <Image src="/logo.png" alt="" width={34} height={34} />
                  </span>
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
