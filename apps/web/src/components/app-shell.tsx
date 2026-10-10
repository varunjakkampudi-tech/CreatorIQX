"use client";

import { LayoutDashboard, CalendarDays, Film, Settings, Sparkles } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { useSession } from "@/lib/session-context";

interface NavItem {
  href: "/dashboard" | "/content/planner" | "/content/videos" | "/settings";
  label: string;
  icon: typeof LayoutDashboard;
}

/**
 * The app shell (spec section 11): a left sidebar for task-based navigation
 * plus a top bar for identity. Every screen under `app/(app)` renders
 * inside this. Nav items here are limited to what the backend actually
 * supports today (planner, video board, settings) - spec section 11 lists
 * more groups (Inbox, Analytics, Intelligence) that later phases add their
 * own routes and screens for, per the "never present fake functionality as
 * real" rule.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const t = useTranslations("AppShell");
  const pathname = usePathname();
  const { isLoading, isSignedIn, email } = useSession();

  const items: NavItem[] = [
    { href: "/dashboard", label: t("navDashboard"), icon: LayoutDashboard },
    { href: "/content/planner", label: t("navPlanner"), icon: CalendarDays },
    { href: "/content/videos", label: t("navVideos"), icon: Film },
    { href: "/settings", label: t("navSettings"), icon: Settings },
  ];

  return (
    <div className="flex min-h-screen bg-surface text-ink">
      <aside className="flex w-60 flex-col border-r border-border bg-surface-raised p-4">
        <div className="mb-6 flex items-center gap-2 px-2">
          <Sparkles aria-hidden="true" className="text-brand" />
          <span className="text-lg font-semibold">{t("productName")}</span>
        </div>
        <nav className="flex flex-1 flex-col gap-1" aria-label={t("productName")}>
          {items.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href || pathname?.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  active
                    ? "bg-brand text-brand-ink"
                    : "text-ink-muted hover:bg-surface hover:text-ink",
                )}
                aria-current={active ? "page" : undefined}
              >
                <Icon aria-hidden="true" className="size-4 shrink-0" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-border pt-4 text-xs text-ink-muted">
          {!isLoading && isSignedIn && email ? (
            <div className="flex flex-col gap-1 px-2">
              <span>{t("signedInAs")}</span>
              <span className="truncate font-medium text-ink">{email}</span>
            </div>
          ) : null}
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-5xl p-8">{children}</div>
      </main>
    </div>
  );
}
