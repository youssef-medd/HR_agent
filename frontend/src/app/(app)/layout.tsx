import { type AttentionItem } from "@/lib/api/client";
import { apiGet, requireUser } from "@/lib/api/server";
import { TopNav } from "@/components/shell/top-nav";
import { BackgroundNoise } from "@/components/ui/background-noise";

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
      {/* Grainy orange spotlight. Scoped to this layout, so the login and the
          public candidate pages keep their own backdrops. */}
      <BackgroundNoise />

      <div className="mx-auto w-full max-w-[1440px] px-4 pt-4 pb-10 md:px-8">
        <TopNav user={user} attentionCount={openCount} />
        {/* Hairline horizon under the nav — separates chrome from content
            without drawing a full border across the ground. */}
        <div className="console-horizon mt-4 h-px w-full" aria-hidden />
        <main className="pt-6">{children}</main>
      </div>
    </div>
  );
}
