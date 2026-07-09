import { NextResponse, type NextRequest } from "next/server";

const SESSION_COOKIE = "welyne_session";

/**
 * Presence check only — the JWT is validated server-side by getServerSession()
 * against GET /auth/me. No JWT_SECRET ever lives in the frontend.
 */
export function middleware(request: NextRequest) {
  const hasSession = request.cookies.has(SESSION_COOKIE);
  const { pathname } = request.nextUrl;

  const isLogin = pathname === "/login";

  if (!hasSession && !isLogin) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }

  if (hasSession && isLogin) {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    url.search = "";
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  // Everything except Next internals, static assets, and the auth BFF routes
  matcher: ["/((?!api/auth|_next/static|_next/image|favicon.ico|.*\\.\\w+$).*)"],
};
