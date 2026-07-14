import { type AttentionItem } from "@/lib/api/client";
import { apiGet, requireUser } from "@/lib/api/server";
import { TopNav } from "@/components/shell/top-nav";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await requireUser();
  const attention = await apiGet<AttentionItem[]>("/needs-attention", []);
  const openCount = attention.filter((a) => a.status === "open").length;

  return (
    <div className="relative min-h-svh overflow-x-clip">
      {/* Cinematic ambient glow — single soft radial spotlight, breathing slowly */}
      <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 bg-background">
        <div
          className="ambient-glow absolute inset-0"
          style={{
            background:
              "radial-gradient(60% 50% at 50% 38%, rgba(255,140,66,0.28), rgba(255,180,120,0.12) 45%, transparent 72%)",
          }}
        />
      </div>

      <div className="mx-auto w-full max-w-[1440px] px-4 pt-4 pb-10 md:px-8">
        <TopNav user={user} attentionCount={openCount} />
        <main className="pt-6">{children}</main>
      </div>
    </div>
  );
}
