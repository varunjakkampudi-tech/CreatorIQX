"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { $api } from "@/lib/api";
import { useSession } from "@/lib/session-context";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { SignInCard } from "@/components/sign-in-card";

const TERMINAL_STATUSES = new Set([
  "published",
  "analyzed",
  "rejected",
  "archived",
]);

export default function DashboardPage() {
  const t = useTranslations("DashboardPage");
  const { isLoading: sessionLoading, isSignedIn } = useSession();

  const plansQuery = $api.useQuery("get", "/api/v1/planner/plans", {
    enabled: isSignedIn,
  });
  const videosQuery = $api.useQuery("get", "/api/v1/videos", {
    enabled: isSignedIn,
  });

  if (sessionLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (!isSignedIn) {
    return <SignInCard />;
  }

  const plans = plansQuery.data ?? [];
  const videos = videosQuery.data ?? [];
  const inMotion = videos.filter((v) => !TERMINAL_STATUSES.has(v.status));
  const published = videos.filter(
    (v) => v.status === "published" || v.status === "analyzed",
  );
  const recentVideos = [...videos].slice(-5).reverse();

  return (
    <div className="flex flex-col gap-8">
      <header>
        <h1 className="text-2xl font-semibold text-ink">{t("title")}</h1>
        <p className="text-sm text-ink-muted">{t("subtitle")}</p>
      </header>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <p className="text-sm text-ink-muted">{t("plansCard")}</p>
          <p className="mt-2 text-3xl font-semibold text-ink">{plans.length}</p>
        </Card>
        <Card>
          <p className="text-sm text-ink-muted">{t("videosCard")}</p>
          <p className="mt-2 text-3xl font-semibold text-ink">
            {inMotion.length}
          </p>
        </Card>
        <Card>
          <p className="text-sm text-ink-muted">{t("publishedCard")}</p>
          <p className="mt-2 text-3xl font-semibold text-ink">
            {published.length}
          </p>
        </Card>
      </div>

      <Card>
        <h2 className="mb-3 text-lg font-semibold text-ink">
          {t("recentVideos")}
        </h2>
        {recentVideos.length === 0 ? (
          <p className="text-sm text-ink-muted">{t("emptyVideos")}</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {recentVideos.map((video) => (
              <li
                key={video.id}
                className="flex items-center justify-between rounded-md border border-border px-3 py-2"
              >
                <span className="truncate text-sm text-ink">{video.title}</span>
                <span className="shrink-0 rounded-full bg-surface px-2 py-0.5 text-xs text-ink-muted">
                  {video.status}
                </span>
              </li>
            ))}
          </ul>
        )}
        <Link
          href="/content/videos"
          className="mt-4 inline-block text-sm font-medium text-brand hover:underline"
        >
          {t("goToVideos")}
        </Link>
      </Card>

      {plans.length === 0 ? (
        <Card>
          <p className="text-sm text-ink-muted">{t("emptyPlans")}</p>
          <Link
            href="/content/planner"
            className="mt-2 inline-block text-sm font-medium text-brand hover:underline"
          >
            {t("goToPlanner")}
          </Link>
        </Card>
      ) : null}
    </div>
  );
}
