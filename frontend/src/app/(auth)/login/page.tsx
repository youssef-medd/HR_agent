import { Suspense } from "react";

import { LoginForm } from "@/components/auth/login-form";

export const metadata = { title: "Sign in · Welyne HR" };

export default function LoginPage() {
  return (
    <main className="grid min-h-svh lg:grid-cols-[1.1fr_1fr]">
      {/* Left panel — editorial brand statement */}
      <section className="relative hidden flex-col justify-between overflow-hidden border-r p-12 lg:flex">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(120% 90% at 15% 110%, rgba(255,107,0,0.14) 0%, transparent 55%), radial-gradient(80% 60% at 90% -10%, rgba(255,107,0,0.05) 0%, transparent 60%)",
          }}
        />
        <header className="relative flex items-center gap-3">
          <span className="bg-primary block size-2.5" aria-hidden />
          <span className="font-heading text-lg font-semibold tracking-tight">
            welyne
          </span>
          <span className="eyebrow ml-1">HR Agent</span>
        </header>

        <div className="relative max-w-md">
          <p className="eyebrow eyebrow-accent mb-4">Recruitment · Supervised AI</p>
          <h1 className="font-heading text-4xl leading-tight font-semibold tracking-tight text-balance">
            Every hire reviewed by a human.
            <br />
            Everything else, automated.
          </h1>
          <p className="text-muted-foreground mt-5 leading-relaxed">
            CV parsing, blind scoring, pre-screening and scheduling — with a
            human gate on every rejection, offer and publication.
          </p>
        </div>

        <footer className="eyebrow relative">
          WE BUILD PRODUCTS &amp; AI — WELYNE.COM
        </footer>
      </section>

      {/* Right panel — form */}
      <section className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="mb-10 lg:hidden">
            <div className="flex items-center gap-3">
              <span className="bg-primary block size-2.5" aria-hidden />
              <span className="font-heading text-lg font-semibold tracking-tight">
                welyne
              </span>
              <span className="eyebrow ml-1">HR Agent</span>
            </div>
          </div>

          <p className="eyebrow mb-2">Console access</p>
          <h2 className="font-heading mb-8 text-2xl font-semibold tracking-tight">
            Sign in to continue
          </h2>

          <Suspense>
            <LoginForm />
          </Suspense>

          <p className="text-muted-foreground mt-8 text-xs leading-relaxed">
            Access is restricted to Welyne recruitment staff. Sessions expire
            after 8 hours.
          </p>
        </div>
      </section>
    </main>
  );
}
