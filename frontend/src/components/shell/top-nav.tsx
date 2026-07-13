"use client";

import * as React from "react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BellRing, Search } from "lucide-react";

import { UploadCvDialog } from "@/components/applications/upload-cv-dialog";
import { cn } from "@/lib/utils";
import type { MeResponse } from "@/lib/api/client";
import { BrandBadge } from "./brand-badge";
import { NAV_ITEMS } from "./nav-config";
import { ThemeToggle } from "./theme-toggle";
import { UserMenu } from "./user-menu";

/** Floating pill navigation bar — logo, pill links, search, alerts, CTA, user. */
export function TopNav({
  user,
  attentionCount,
}: {
  user: MeResponse;
  attentionCount: number;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [query, setQuery] = React.useState("");

  const items = NAV_ITEMS.filter(
    (item) => !item.roles || item.roles.includes(user.role),
  );

  function onSearch(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const q = query.trim();
    router.push(q ? `/candidates?q=${encodeURIComponent(q)}` : "/candidates");
  }

  return (
    <header className="surface flex items-center justify-between gap-3 px-4 py-3 md:px-5">
      {/* Brand */}
      <Link href="/" className="flex shrink-0 items-center gap-2.5">
        <Image src="/logo.png" alt="Welyne" width={32} height={32} priority />
        <span className="font-heading hidden text-base font-semibold tracking-tight sm:inline">
          welyne
        </span>
        <span className="bg-border hidden h-4 w-px md:inline-block" aria-hidden />
        <BrandBadge className="hidden md:inline-flex" />
      </Link>

      {/* Pill nav */}
      <nav className="bg-muted flex items-center gap-1 overflow-x-auto rounded-full p-1">
        {items.map((item) => {
          const active =
            item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-2 rounded-full px-3.5 py-2 text-sm whitespace-nowrap transition-colors duration-200",
                active
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground hover:bg-card",
              )}
            >
              <item.icon className="size-4" aria-hidden />
              <span className="hidden xl:inline">{item.title}</span>
            </Link>
          );
        })}
      </nav>

      {/* Search + alerts + CTA + user */}
      <div className="flex shrink-0 items-center gap-2">
        <form onSubmit={onSearch} className="relative hidden lg:block">
          <Search
            className="text-muted-foreground pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2"
            aria-hidden
          />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search candidates"
            aria-label="Search candidates"
            className="bg-muted placeholder:text-muted-foreground focus-visible:ring-ring h-10 w-44 rounded-full pr-4 pl-10 text-sm outline-none focus-visible:ring-2"
          />
        </form>

        <Link
          href="/attention"
          aria-label={`Needs attention — ${attentionCount} open`}
          className="bg-muted text-muted-foreground hover:text-foreground relative flex size-10 items-center justify-center rounded-full transition-colors duration-200"
        >
          <BellRing className="size-4" aria-hidden />
          {attentionCount > 0 && (
            <span className="bg-primary absolute -top-0.5 -right-0.5 flex size-4.5 items-center justify-center rounded-full font-mono text-[9px] font-bold text-white">
              {attentionCount > 9 ? "9+" : attentionCount}
            </span>
          )}
        </Link>

        <ThemeToggle />

        <div className="hidden sm:block">
          <UploadCvDialog />
        </div>

        <UserMenu user={user} />
      </div>
    </header>
  );
}
