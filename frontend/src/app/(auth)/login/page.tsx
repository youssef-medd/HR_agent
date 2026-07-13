import { Suspense } from "react";

import { CinematicLogin } from "@/components/auth/cinematic-login";

export const metadata = { title: "Sign in · Welyne HR" };

export default function LoginPage() {
  return (
    <Suspense>
      <CinematicLogin />
    </Suspense>
  );
}
