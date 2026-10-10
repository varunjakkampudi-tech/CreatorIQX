"use client";

import { useTranslations } from "next-intl";
import { $api } from "@/lib/api";
import { useSession } from "@/lib/session-context";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { SignInCard } from "@/components/sign-in-card";

/** Settings (spec section 4 #20 / section 11): account and workspace info. */
export default function SettingsPage() {
  const t = useTranslations("SettingsPage");
  const {
    isLoading: sessionLoading,
    isSignedIn,
    csrfToken,
    email,
  } = useSession();

  const meQuery = $api.useQuery("get", "/api/v1/me", { enabled: isSignedIn });
  const workspaceQuery = $api.useQuery("get", "/api/v1/workspaces/current", {
    enabled: isSignedIn,
  });

  const signOut = $api.useMutation("post", "/api/v1/auth/logout", {
    onSuccess: () => {
      window.location.href = "/";
    },
  });

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

  function handleSignOut() {
    if (!csrfToken) {
      return;
    }
    signOut.mutate({ headers: { "X-CSRF-Token": csrfToken } });
  }

  return (
    <div className="flex flex-col gap-8">
      <header>
        <h1 className="text-2xl font-semibold text-ink">{t("title")}</h1>
        <p className="text-sm text-ink-muted">{t("subtitle")}</p>
      </header>

      <Card>
        <h2 className="mb-3 text-lg font-semibold text-ink">
          {t("accountSection")}
        </h2>
        <dl className="flex flex-col gap-2 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-ink-muted">{t("email")}</dt>
            <dd className="text-ink">{meQuery.data?.email ?? email}</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt className="text-ink-muted">{t("role")}</dt>
            <dd className="text-ink">{meQuery.data?.role ?? "—"}</dd>
          </div>
        </dl>
      </Card>

      <Card>
        <h2 className="mb-3 text-lg font-semibold text-ink">
          {t("workspaceSection")}
        </h2>
        <dl className="flex flex-col gap-2 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-ink-muted">{t("workspaceName")}</dt>
            <dd className="text-ink">{workspaceQuery.data?.name ?? "—"}</dd>
          </div>
        </dl>
      </Card>

      <div>
        <Button
          variant="secondary"
          onClick={handleSignOut}
          disabled={signOut.isPending}
        >
          {t("signOut")}
        </Button>
      </div>
    </div>
  );
}
