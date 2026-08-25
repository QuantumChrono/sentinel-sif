/**
 * The one Supabase client the browser uses, and the role -> landing-page rule.
 *
 * NEXT_PUBLIC_ VARIABLES ONLY, AND ONLY THE ANON KEY. Every `NEXT_PUBLIC_` value is inlined into
 * the JavaScript bundle Next.js ships to the browser, so it is public the moment the page loads.
 * A `SUPABASE_SERVICE_ROLE_KEY` placed in any variable under `frontend/` would hand every visitor
 * unrestricted read and write access to all six tables, RLS bypassed. The service-role key belongs
 * in `backend/.env` and nowhere else. There is no import of it here and there must never be one.
 *
 * WHAT THIS CLIENT IS FOR: authentication only - sign in, sign out, read the current session.
 * It is NOT a second data path. Report and analytics data comes from the FastAPI backend through
 * `api_client.ts`, which is the single HTTP layer. Reading tables directly from the browser would
 * be a second set of queries with no server-side validation in front of them, and it does not
 * currently work in any case: the anon role has no grants on these tables (`AUDIT.md` 2026-08-25,
 * `42501 permission denied` on `sites`).
 *
 * The role and redirect rules are NOT here - they are pure functions in `user_role.ts`, which
 * `middleware.ts` can import without dragging this browser client into the Edge runtime.
 */

import { createBrowserClient } from "@supabase/ssr";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

if (!url || !anonKey) {
  // Thrown rather than defaulted: a client built from a missing URL fails later with a network
  // error that reads like the server is down, which sends you debugging the wrong machine.
  throw new Error(
    "Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and " +
      "NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend/.env.local (see frontend/.env.example).",
  );
}

export const supabase = createBrowserClient(url, anonKey);
