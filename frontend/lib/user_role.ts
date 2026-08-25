/**
 * Two pure functions: which role a session claims, and where that role lands.
 *
 * SEPARATE FROM `supabase_client.ts` ON PURPOSE. `middleware.ts` runs in the Edge runtime and
 * needs both of these, but `supabase_client.ts` builds a BROWSER client at module load and throws
 * there when the env vars are missing - importing it into middleware would drag a `document`-based
 * client and a module-level throw into a runtime that has neither. Keeping the rules here means
 * middleware, the header and the login page all read one copy of them, with nothing to construct.
 *
 * Both take plain values, so `role_check.ts` asserts them without a browser or a live session.
 */

/** The signed-in user's role, read from `app_metadata` and NOT from `user_metadata`.
 *
 * THIS DISTINCTION IS THE WHOLE SECURITY BOUNDARY. `user_metadata` is writable by the user
 * themselves via `supabase.auth.updateUser({ data: ... })`, so a role kept there lets any site
 * supervisor promote themselves to `hse_manager` from the browser console. `app_metadata` is
 * writable only with the service-role key, which lives on the backend, so a claim there is one
 * the user cannot forge.
 *
 * Returns null when the claim is absent - which is what every account looks like until the demo
 * users are created with it set (`DIY.md`, Day 1). Null lands on `/intake` by the rule below.
 */
export function roleFromAppMetadata(
  appMetadata: Record<string, unknown> | undefined | null,
): string | null {
  const role = appMetadata?.role;
  return typeof role === "string" && role.length > 0 ? role : null;
}

/** Where a signed-in user lands, from `PRD.md` § Frontend pages item 1: `hse_manager` reads the
 * aggregate view, `site_supervisor` files reports.
 *
 * `admin` is a third role in `schema.sql` that `PRD.md` gives no redirect for; it goes to the
 * dashboard, the more privileged of the two screens. An absent or unrecognised role goes to
 * `/intake`, the lesser-privileged one - a missing claim must never open the management view.
 */
export function landingPageForRole(role: string | null | undefined): "/dashboard" | "/intake" {
  return role === "hse_manager" || role === "admin" ? "/dashboard" : "/intake";
}
