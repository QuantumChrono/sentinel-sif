/**
 * The authentication boundary for the whole app: no signed-in session, no authenticated page.
 *
 * WHY THIS RUNS IN MIDDLEWARE AND NOT IN A `useEffect` GUARD. A client-side check renders the page
 * first and redirects afterwards, so an unauthenticated visitor to `/dashboard` sees a frame of
 * real KPI numbers before being sent away. That is the exact failure the brief forbids. Middleware
 * runs before any page is sent, so the redirect happens instead of the render, not after it.
 *
 * `getUser()` IS DELIBERATE, NOT `getSession()`. `getSession()` decodes the cookie and trusts it;
 * `getUser()` verifies the JWT with Supabase, so a hand-edited cookie claiming `hse_manager` fails
 * here. It costs one network round trip per protected request, which is the correct price.
 *
 * WHAT THIS IS NOT. This protects the pages. It does NOT protect the FastAPI backend, which today
 * has no authentication on any endpoint and holds the service-role key - anyone who knows its URL
 * can read and write every table with `curl`, signed in or not. Logged as a real finding in
 * `AUDIT.md` (2026-08-26, security, high) rather than hidden behind this file, because a route
 * guard that looks like a security boundary while the API stays open is worse than an open API
 * nobody was misled about.
 */

import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { landingPageForRole, roleFromAppMetadata } from "./lib/user_role";

/** Pages that require a session. `/` is included: it must land a signed-in user on their role's
 * screen and send everyone else to the login page, never render as a public shell. */
const PROTECTED_PREFIXES = ["/", "/intake", "/reports", "/dashboard", "/review"];

function isProtected(pathname: string): boolean {
  return PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || (prefix !== "/" && pathname.startsWith(`${prefix}/`)),
  );
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Cookies must be written onto the response that is actually returned, so it is created up
  // front and handed to the client below - otherwise a refreshed token is verified here and then
  // thrown away, and the user is signed out again on the next request.
  const response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (cookiesToSet) => {
          for (const { name, value, options } of cookiesToSet) {
            request.cookies.set(name, value);
            response.cookies.set(name, value, options);
          }
        },
      },
    },
  );

  const { data, error } = await supabase.auth.getUser();
  const user = error ? null : data.user;

  if (!user && isProtected(pathname)) {
    const redirect = request.nextUrl.clone();
    redirect.pathname = "/login";
    // Where they were headed, so the login page can return them there instead of to a generic
    // landing screen. Read back with `searchParams.get("next")`.
    redirect.search = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname)}`;
    return NextResponse.redirect(redirect);
  }

  // A signed-in user has no business on the login form, and `/` is not a page in this app - both
  // resolve to the landing screen for their role (`PRD.md` § Frontend pages item 1).
  if (user && (pathname === "/login" || pathname === "/")) {
    const redirect = request.nextUrl.clone();
    redirect.pathname = landingPageForRole(roleFromAppMetadata(user.app_metadata));
    redirect.search = "";
    return NextResponse.redirect(redirect);
  }

  return response;
}

export const config = {
  // Static assets and image optimisation are excluded: running an auth round trip per font file
  // would slow every page for no protection. Everything else passes through `isProtected`.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};
