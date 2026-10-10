"use client";

import { useTranslations } from "next-intl";
import { $api } from "@/lib/api";
import { useSession } from "@/lib/session-context";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { SignInCard } from "@/components/sign-in-card";

/**
 * The video board (spec section 11: "Video Board (kanban of the state
 * machine)"). Columns follow the domain's VideoStatus order exactly
 * (identity/video state machine: idea -> ... -> analyzed, plus rejected
 * and archived) so a card's column always matches its real backend state -
 * there is no separate "UI status" to drift from it.
 */
const STATUS_ORDER = [
  "idea",
  "planned",
  "drafting",
  "qa",
  "in_review",
  "approved",
  "scheduled",
  "published",
  "analyzed",
  "rejected",
  "archived",
] as const;

export default function VideosPage() {
  const t = useTranslations("VideosPage");
  const { isLoading: sessionLoading, isSignedIn } = useSession();

  const videosQuery = $api.useQuery("get", "/api/v1/videos", {
    enabled: isSignedIn,
  });

  if (sessionLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!isSignedIn) {
    return <SignInCard />;
  }

  const videos = videosQuery.data ?? [];
  const byStatus = new Map<string, typeof videos>();
  for (const status of STATUS_ORDER) {
    byStatus.set(status, []);
  }
  for (const video of videos) {
    const bucket = byStatus.get(video.status);
    if (bucket) {
      bucket.push(video);
    } else {
      byStatus.set(video.status, [video]);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold text-ink">{t("title")}</h1>
        <p className="text-sm text-ink-muted">{t("subtitle")}</p>
      </header>

      <div className="flex gap-4 overflow-x-auto pb-2">
        {STATUS_ORDER.map((status) => {
          const columnVideos = byStatus.get(status) ?? [];
          return (
            <div key={status} className="flex w-64 shrink-0 flex-col gap-2">
              <div className="flex items-center justify-between px-1">
                <span className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
                  {t(`status.${status}`)}
                </span>
                <span className="rounded-full bg-surface-raised px-2 py-0.5 text-xs text-ink-muted">
                  {columnVideos.length}
                </span>
              </div>
              <div className="flex flex-col gap-2">
                {columnVideos.length === 0 ? (
                  <Card className="text-xs text-ink-muted">{t("empty")}</Card>
                ) : (
                  columnVideos.map((video) => (
                    <Card key={video.id} className="flex flex-col gap-1">
                      <span className="text-sm font-medium text-ink">
                        {video.title || t("untitled")}
                      </span>
                    </Card>
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
