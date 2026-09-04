import Image from "next/image";

import { PublicBackdrop } from "@/components/apply/public-backdrop";
import { BrandBadge } from "@/components/shell/brand-badge";

/**
 * Chrome for the public candidate pages (job list, application, portal).
 *
 * Deliberately continuous with the cinematic login: black ground, orange dot
 * field, the same floating pill navbar. A candidate who clicks through from
 * the login should feel they are still inside the same product, not on a
 * different site.
 */
export function PublicShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative min-h-svh bg-black">
      <PublicBackdrop />

      <header className="relative z-20 mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <div className="flex items-center gap-2.5">
          <Image src="/logo.png" alt="Welyne" width={26} height={26} />
          <span className="font-heading text-sm font-semibold tracking-tight text-white">
            welyne
          </span>
        </div>
        <BrandBadge tone="dark" />
        <a
          href="https://welyne.com"
          target="_blank"
          rel="noreferrer"
          className="hidden text-xs text-white/40 transition-colors duration-200 hover:text-white sm:block"
        >
          welyne.com
        </a>
      </header>

      <main className="relative z-10 mx-auto max-w-6xl px-6 pb-16">{children}</main>
    </div>
  );
}

/**
 * Dark glass card — the surface the page content sits on.
 *
 * Opaque enough to stay readable over the animated dot field behind it: the
 * blur plus a near-black tint stops the moving shader from showing through the
 * body copy, while the border keeps the glass edge visible.
 */
export function GlassCard({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-3xl border border-white/12 bg-gradient-to-br from-white/[0.09] via-white/[0.05] to-white/[0.03] shadow-[0_8px_40px_rgba(0,0,0,0.45)] backdrop-blur-xl ${className}`}
    >
      {children}
    </div>
  );
}
