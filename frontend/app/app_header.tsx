"use client";

/**
 * The header: product name, who is signed in, the two navigation links, and sign out.
 *
 * A client component because sign-out is an interaction and the session is read in the browser.
 * It renders NOTHING until a user is confirmed, so the login page - which the shell also wraps -
 * does not show navigation into pages the visitor cannot open yet.
 *
 * The role shown here is `app_metadata.role`, the same claim `middleware.ts` redirects on. It is
 * displayed rather than hidden because until the two demo accounts are created with it set
 * (`DIY.md`, Day 1) every account reads "no role set", and that is worth seeing on screen instead
 * of inferring from which page you landed on.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { supabase } from "@/lib/supabase_client";
import { roleFromAppMetadata } from "@/lib/user_role";

const ROLE_LABELS: Record<string, string> = {
  hse_manager: "HSE manager",
  site_supervisor: "Site supervisor",
  admin: "Administrator",
};

export function AppHeader() {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);

  useEffect(() => {
    // `onAuthStateChange` fires once with the current session on subscribe, so this covers both
    // the initial read and every later sign-in or sign-out without a separate `getUser()` call.
    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      setEmail(session?.user.email ?? null);
      setRole(roleFromAppMetadata(session?.user.app_metadata));
    });
    return () => data.subscription.unsubscribe();
  }, []);

  if (!email) return null;

  async function signOut() {
    await supabase.auth.signOut();
    router.replace("/login");
  }

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-6 py-3">
        <span className="font-semibold tracking-tight">SentinelSIF</span>
        <nav aria-label="Main" className="flex gap-4 text-sm">
          <Link href="/intake" className="rounded underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900">
            Submit report
          </Link>
          <Link href="/dashboard" className="rounded underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900">
            Dashboard
          </Link>
          {/* The review queue is reachable by every signed-in role. The queue is a workflow, not a
              privileged view: a site supervisor who submitted a low-confidence report is often the
              person who can say what actually happened. Whether it becomes role-gated is a decision
              for whoever owns the privilege rule, not something to assume here. */}
          <Link href="/review" className="rounded underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900">
            Review queue
          </Link>
        </nav>
        <div className="ml-auto flex items-center gap-3 text-sm">
          <span className="text-slate-600">
            {email}
            <span className="ml-1 text-slate-400">
              ({role ? ROLE_LABELS[role] ?? role : "no role set"})
            </span>
          </span>
          <button
            type="button"
            onClick={signOut}
            className="rounded border border-slate-300 px-3 py-1 font-medium hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900"
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
