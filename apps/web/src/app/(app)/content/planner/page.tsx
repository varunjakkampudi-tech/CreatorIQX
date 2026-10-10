"use client";

import { useState, type FormEvent } from "react";
import { useTranslations } from "next-intl";
import { $api } from "@/lib/api";
import { useSession } from "@/lib/session-context";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { SignInCard } from "@/components/sign-in-card";

/**
 * The Planner (spec section 4 #4, section 11): the creator's backlog,
 * grouped by series - closest in spirit to a series-style board. A plan
 * becomes a Video in one click via POST .../promote (acceptance
 * criterion: "Plans persist and can become Video records in one click").
 */
export default function PlannerPage() {
  const t = useTranslations("PlannerPage");
  const { isLoading: sessionLoading, isSignedIn, csrfToken } = useSession();

  const plansQuery = $api.useQuery("get", "/api/v1/planner/plans", {
    enabled: isSignedIn,
  });

  const createPlan = $api.useMutation("post", "/api/v1/planner/plans", {
    onSuccess: () => {
      void plansQuery.refetch();
      setTitle("");
      setSeries("");
      setNotes("");
    },
  });

  const promotePlan = $api.useMutation(
    "post",
    "/api/v1/planner/plans/{plan_id}/promote",
    {
      onSuccess: () => {
        void plansQuery.refetch();
      },
    },
  );

  const [title, setTitle] = useState("");
  const [series, setSeries] = useState("");
  const [notes, setNotes] = useState("");

  if (sessionLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!isSignedIn) {
    return <SignInCard />;
  }

  const plans = plansQuery.data ?? [];
  const groups = new Map<string, typeof plans>();
  for (const plan of plans) {
    const key = plan.series ?? t("noSeries");
    const existing = groups.get(key);
    if (existing) {
      existing.push(plan);
    } else {
      groups.set(key, [plan]);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!title.trim() || !csrfToken) {
      return;
    }
    createPlan.mutate({
      headers: { "X-CSRF-Token": csrfToken },
      body: {
        title: title.trim(),
        notes,
        series: series.trim() ? series.trim() : null,
        scheduled_date: null,
      },
    });
  }

  function handlePromote(planId: string) {
    if (!csrfToken) {
      return;
    }
    promotePlan.mutate({
      headers: { "X-CSRF-Token": csrfToken },
      params: { path: { plan_id: planId } },
    });
  }

  return (
    <div className="flex flex-col gap-8">
      <header>
        <h1 className="text-2xl font-semibold text-ink">{t("title")}</h1>
        <p className="text-sm text-ink-muted">{t("subtitle")}</p>
      </header>

      <Card>
        <h2 className="mb-3 text-lg font-semibold text-ink">{t("newIdea")}</h2>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <label htmlFor="plan-title" className="text-sm font-medium text-ink">
              {t("titleLabel")}
            </label>
            <Input
              id="plan-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t("titlePlaceholder")}
              required
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="plan-series" className="text-sm font-medium text-ink">
              {t("seriesLabel")}
            </label>
            <Input
              id="plan-series"
              value={series}
              onChange={(e) => setSeries(e.target.value)}
              placeholder={t("seriesPlaceholder")}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="plan-notes" className="text-sm font-medium text-ink">
              {t("notesLabel")}
            </label>
            <Input
              id="plan-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={t("notesPlaceholder")}
            />
          </div>
          {createPlan.isError ? (
            <p className="text-sm text-danger">{t("error")}</p>
          ) : null}
          <Button type="submit" disabled={createPlan.isPending || !title.trim()}>
            {createPlan.isPending ? t("adding") : t("add")}
          </Button>
        </form>
      </Card>

      {plans.length === 0 ? (
        <Card>
          <p className="text-sm text-ink-muted">{t("empty")}</p>
        </Card>
      ) : (
        <div className="flex flex-col gap-6">
          {[...groups.entries()].map(([seriesName, seriesPlans]) => (
            <div key={seriesName} className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-muted">
                {seriesName}
              </h3>
              <div className="flex flex-col gap-2">
                {seriesPlans.map((plan) => (
                  <Card key={plan.id} className="flex items-center justify-between gap-4">
                    <div className="flex flex-col gap-1">
                      <span className="text-sm font-medium text-ink">{plan.title}</span>
                      {plan.notes ? (
                        <span className="text-xs text-ink-muted">{plan.notes}</span>
                      ) : null}
                    </div>
                    {plan.promoted_video_id ? (
                      <span className="shrink-0 rounded-full bg-success/10 px-3 py-1 text-xs font-medium text-success">
                        {t("promoted")}
                      </span>
                    ) : (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => handlePromote(plan.id)}
                        disabled={promotePlan.isPending}
                      >
                        {promotePlan.isPending ? t("promoting") : t("promote")}
                      </Button>
                    )}
                  </Card>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
