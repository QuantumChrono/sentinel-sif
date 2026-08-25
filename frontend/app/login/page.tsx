"use client";

/**
 * Sign in, then land on the page this account's role owns (`PRD.md` § Frontend pages item 1).
 *
 * The redirect target comes from `landingPageForRole`, the same pure rule `middleware.ts` applies,
 * so signing in and navigating directly can never disagree about where a role belongs.
 *
 * `?next=` is honoured when present - middleware records where an unauthenticated visitor was
 * headed, and sending them to a generic landing page instead would lose a shared report link.
 * Only same-site paths are accepted; see below.
 *
 * It is read from `window.location` inside the submit handler rather than with `useSearchParams`,
 * which forces this page into a Suspense boundary and fails the production build without one. The
 * value is only needed once the user has submitted, by which point `window` certainly exists, so
 * the hook bought nothing here.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import { supabase } from "@/lib/supabase_client";
import { landingPageForRole, roleFromAppMetadata } from "@/lib/user_role";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  /** A `next` value is a URL the visitor controls, so only a same-site absolute path is accepted:
   * `//evil.example` and `https://evil.example` are both valid relative-looking inputs to
   * `router.replace` and would turn our login form into an open redirect. */
  function safeNext(): string | null {
    const next = new URLSearchParams(window.location.search).get("next");
    return next && next.startsWith("/") && !next.startsWith("//") ? next : null;
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    const { data, error: signInError } = await supabase.auth.signInWithPassword({ email, password });

    if (signInError) {
      // Supabase's own message is shown: it distinguishes bad credentials from an unconfirmed
      // email, and replacing both with one sentence would hide a fixable setup problem.
      setError(signInError.message);
      setSubmitting(false);
      return;
    }

    // `replace`, not `push`: the login form must not be a back-button destination once signed in.
    router.replace(safeNext() ?? landingPageForRole(roleFromAppMetadata(data.user.app_metadata)));
  }

  return (
    <div className="mx-auto max-w-sm py-12">
      <h1 className="text-2xl font-semibold tracking-tight">Sign in to SentinelSIF</h1>
      <p className="mt-2 text-sm text-slate-600">
        Serious Injury and Fatality potential detection for field HSE reports.
      </p>

      <form onSubmit={handleSubmit} className="mt-8 space-y-4">
        <div>
          <label htmlFor="email" className="block text-sm font-medium">
            Work email
          </label>
          <input
            id="email"
            name="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mt-1 w-full rounded border border-slate-300 bg-white px-3 py-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900"
          />
        </div>

        <div>
          <label htmlFor="password" className="block text-sm font-medium">
            Password
          </label>
          <input
            id="password"
            name="password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-1 w-full rounded border border-slate-300 bg-white px-3 py-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900"
          />
        </div>

        {/* `role="alert"` so the failure is announced, not only shown. */}
        {error && (
          <p role="alert" className="rounded border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-900">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded bg-slate-900 px-4 py-2 font-medium text-white hover:bg-slate-800 disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900"
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
