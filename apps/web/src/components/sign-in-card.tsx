import { LogIn } from "lucide-react";
import { useTranslations } from "next-intl";
import { Card } from "@/components/ui/card";

/**
 * Shown on any `(app)` screen when `/api/v1/auth/session` has no session.
 * `/api/v1/auth/login` is a plain redirect (identity/api/auth.py), not a
 * JSON endpoint, so this is a real anchor, not a typed API call - the
 * browser navigates away to Google and back through `/auth/callback`.
 */
export function SignInCard() {
  const t = useTranslations("SignInCard");
  return (
    <Card className="mx-auto mt-16 flex max-w-md flex-col items-center gap-4 p-8 text-center">
      <LogIn aria-hidden="true" className="size-8 text-brand" />
      <h2 className="text-xl font-semibold text-ink">{t("title")}</h2>
      <p className="text-sm text-ink-muted">{t("body")}</p>
      <a
        href="/api/v1/auth/login"
        className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-brand px-4 py-2 text-base font-medium text-brand-ink transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
      >
        {t("cta")}
      </a>
    </Card>
  );
}
