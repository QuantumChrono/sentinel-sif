import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SentinelSIF",
  description: "Serious Injury and Fatality potential detection for field HSE reports",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
