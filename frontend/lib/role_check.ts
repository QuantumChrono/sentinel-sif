/**
 * Self-check for the two role rules. Run: `node lib/role_check.ts` from `frontend/`.
 *
 * Six lines of branching would not normally earn a check, but these two decide PRIVILEGE: the
 * default for an unknown or missing role, and which metadata field is trusted. Both are the kind
 * of rule that inverts silently under an innocent-looking edit, and neither can be exercised
 * without creating real accounts otherwise.
 */

import { landingPageForRole, roleFromAppMetadata } from "./user_role.ts";

function assert(condition: boolean, label: string) {
  if (!condition) throw new Error(`role_check failed: ${label}`);
}

// The two redirects `PRD.md` § Frontend pages item 1 specifies.
assert(landingPageForRole("hse_manager") === "/dashboard", "hse_manager -> /dashboard");
assert(landingPageForRole("site_supervisor") === "/intake", "site_supervisor -> /intake");

// `admin` exists in `schema.sql` with no PRD redirect; it gets the more privileged screen.
assert(landingPageForRole("admin") === "/dashboard", "admin -> /dashboard");

// Every unknown, absent or malformed role must land on the LESSER-privileged screen. A regression
// here would open the management view to an account with no claim at all.
assert(landingPageForRole(null) === "/intake", "null -> /intake");
assert(landingPageForRole(undefined) === "/intake", "undefined -> /intake");
assert(landingPageForRole("") === "/intake", "empty string -> /intake");
assert(landingPageForRole("HSE_MANAGER") === "/intake", "wrong case is not hse_manager");
assert(landingPageForRole("hse_manager_trainee") === "/intake", "prefix match is not hse_manager");

// The claim is read only when it is a non-empty string.
assert(roleFromAppMetadata({ role: "hse_manager" }) === "hse_manager", "reads app_metadata.role");
assert(roleFromAppMetadata({}) === null, "absent claim -> null");
assert(roleFromAppMetadata(undefined) === null, "no metadata -> null");
assert(roleFromAppMetadata({ role: "" }) === null, "empty claim -> null");
assert(roleFromAppMetadata({ role: 7 }) === null, "non-string claim -> null");
assert(roleFromAppMetadata({ role: ["hse_manager"] }) === null, "array claim -> null");

// An account whose role sits in `user_metadata` - which the user can write themselves - must not
// be read as a role at all. This is the forgery path the two fields exist to separate.
assert(roleFromAppMetadata({ user_metadata: { role: "hse_manager" } }) === null,
  "user_metadata.role is never trusted");

console.log("role_check: 16/16 cases passed");
