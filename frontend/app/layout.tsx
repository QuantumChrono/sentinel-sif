/**
 * The app shell. FROZEN (`STAGES.md` § FROZEN files) - four lanes render inside it for three days.
 *
 * It holds the document, the global stylesheet, the header, and a skip link. It holds no provider
 * and no state: nothing in this app has two consumers that need shared client state yet, and a
 * context added before that is a wrapper every lane has to read around to find the real page.
 * When a second consumer genuinely appears, add it then.
 *
 * Authentication is NOT enforced here. `middleware.ts` redirects before a protected page is ever
 * rendered, which is what stops an unauthenticated visitor seeing a frame of real data first.
 */

import type { Metadata } from "next";
import "./globals.css";
import { AppHeader } from "./app_header";

export const metadata: Metadata = {
  title: "SentinelSIF",
  description: "Serious Injury and Fatality potential detection for field HSE reports",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        {/* First tab stop on every page: a keyboard user reaching the report text should not have
            to tab through the whole header to get there. Visible only when focused. */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-slate-900 focus:px-4 focus:py-2 focus:text-white"
        >
          Skip to main content
        </a>
        <AppHeader />
        <main id="main" className="mx-auto max-w-5xl px-6 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
