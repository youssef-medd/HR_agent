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
      {/* Cinematic ambient glow — drifting peach/orange radials behind the console */}
      <div aria-hidden className="pointer-events-none fixed inset-0 -z-10">
        <div
          className="ambient-blob left-[15%] top-[10%] h-[55vh] w-[55vw] opacity-70 dark:opacity-25"
          style={{
            background:
              "radial-gradient(closest-side, rgba(255,153,102,0.55), transparent 70%)",
          }}
        />
        <div
          className="ambient-blob ambient-blob-2 right-[5%] bottom-[0%] h-[50vh] w-[45vw] opacity-60 dark:opacity-20"
          style={{
            background:
              "radial-gradient(closest-side, rgba(255,107,0,0.35), transparent 70%)",
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
