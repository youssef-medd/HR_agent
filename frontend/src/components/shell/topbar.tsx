import type { MeResponse } from "@/lib/api/client";
import { UserMenu } from "./user-menu";

export function Topbar({ user }: { user: MeResponse }) {
  return (
    <header className="flex h-14 items-center justify-between border-b px-6 md:px-8">
      <p className="eyebrow">
        Recruitment console
        <span className="text-primary mx-2" aria-hidden>
          /
        </span>
        {user.role}
      </p>
      <UserMenu user={user} />
    </header>
  );
}
