import { PageHeader } from "@/components/shell/page-header";
import { type MessageRow } from "@/lib/api/client";
import { apiGet } from "@/lib/api/server";

export const metadata = { title: "Messages · Welyne HR" };
export const dynamic = "force-dynamic";

const CHANNEL_TONE: Record<string, string> = {
  email: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  whatsapp: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
};

const STATUS_TONE: Record<string, string> = {
  sent: "text-emerald-600 dark:text-emerald-400",
  stub: "text-muted-foreground",
  skipped_rate_limited: "text-amber-600 dark:text-amber-400",
  failed: "text-red-600 dark:text-red-400",
};

export default async function MessagesPage() {
  const rows = await apiGet<MessageRow[]>("/reports/messages?limit=200", []);

  return (
    <>
      <PageHeader
        eyebrow="Communications"
        title="Message center"
        description="Every outbound candidate message (A7) — template, channel, delivery status, and the exact body sent. Fully logged; nothing sends off-log."
      />

      {rows.length === 0 ? (
        <div className="surface text-muted-foreground px-6 py-16 text-center text-sm">
          No messages sent yet.
        </div>
      ) : (
        <div className="surface overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-muted-foreground border-b text-left text-xs">
                <th className="px-4 py-3 font-medium">When</th>
                <th className="px-4 py-3 font-medium">Recipient</th>
                <th className="px-4 py-3 font-medium">Channel</th>
                <th className="px-4 py-3 font-medium">Template</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Body</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.id} className="border-b last:border-0 align-top">
                  <td className="text-muted-foreground px-4 py-3 whitespace-nowrap text-xs">
                    {new Date(m.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">{m.recipient}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs ${CHANNEL_TONE[m.channel] ?? "bg-muted"}`}
                    >
                      {m.channel}
                    </span>
                  </td>
                  <td className="text-muted-foreground px-4 py-3 whitespace-nowrap text-xs">
                    {m.template_id ?? "—"}
                  </td>
                  <td className={`px-4 py-3 text-xs ${STATUS_TONE[m.status] ?? ""}`}>
                    {m.status.replace(/_/g, " ")}
                  </td>
                  <td className="text-muted-foreground max-w-md px-4 py-3 text-xs">
                    <span className="line-clamp-2">{m.body}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
