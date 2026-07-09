import { redirect } from "next/navigation";

import { requireUser } from "@/lib/api/server";
import { PageHeader } from "@/components/shell/page-header";
import { ChatPanel } from "@/components/chat/chat-panel";

export const metadata = { title: "Chat · Welyne HR" };

export default async function ChatPage() {
  const user = await requireUser();
  // Mirrors require_role("admin", "recruiter") on POST /chat/hello
  if (user.role === "viewer") redirect("/");

  return (
    <>
      <PageHeader
        eyebrow="LLM gateway"
        title="Smoke test"
        description="Round-trips POST /chat/hello through the Groq → Gemini → Mistral fallback chain. Every call emits a Langfuse trace."
      />
      <ChatPanel />
    </>
  );
}
