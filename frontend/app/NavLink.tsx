"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentProps, ReactNode } from "react";

type NavLinkProps = {
  href: ComponentProps<typeof Link>["href"];
  children: ReactNode;
  className?: string;
};

export default function NavLink({ href, children, className = "" }: NavLinkProps) {
  const pathname = usePathname();
  const active = pathname === href;

  return (
    <Link
      href={href}
      className={`${
        active ? "underline" : ""
      } rounded underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900 ${className}`}
    >
      {children}
    </Link>
  );
}
