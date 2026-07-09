"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";
import type { Role } from "@/lib/api/client";
import { NAV_ITEMS } from "./nav-config";

export function AppSidebar({ role }: { role: Role }) {
  const pathname = usePathname();

  const items = NAV_ITEMS.filter(
    (item) => !item.roles || item.roles.includes(role)
  );

  return (
    <aside className="bg-sidebar sticky top-0 hidden h-svh w-60 shrink-0 flex-col border-r md:flex">
      <div className="flex items-center gap-3 px-5 py-6">
        <span className="bg-primary block size-2.5" aria-hidden />
        <span className="font-heading text-base font-semibold tracking-tight">
          welyne
        </span>
        <span className="eyebrow">HR</span>
      </div>

      <nav className="flex-1 space-y-0.5 px-3">
        <p className="eyebrow px-2 pt-2 pb-3">Recruitment</p>
        {items.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 px-2 py-2 text-sm transition-colors duration-200",
                active
                  ? "bg-accent text-foreground border-primary border-l-2 pl-[6px]"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
              )}
            >
              <item.icon className="size-4" aria-hidden />
              {item.title}
            </Link>
          );
        })}
      </nav>

      <div className="px-5 py-5">
        <p className="eyebrow">v0.1 · Sprint 2</p>
      </div>
    </aside>
  );
}
