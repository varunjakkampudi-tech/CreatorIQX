import { Sparkles } from "lucide-react";
import { getTranslations } from "next-intl/server";
import productConfig from "@creatoriqx/config/product.json" with { type: "json" };
import { cn } from "@/lib/utils";

/**
 * Frontend-foundation placeholder (P0-080/P0-082), not a product screen. The
 * named UI screens in spec section 11 (onboarding, video board, the
 * Video Workspace, approval diff, YouTube Sync) wait on P0-090's
 * written wireframe approval. This page exists only to prove the
 * design tokens render correctly in light and dark using Tailwind
 * utilities alone — every color below is a token utility (bg-surface,
 * text-ink, ...), never a raw hex literal, which is also enforced by
 * eslint.config.mjs. Its one piece of UI copy comes from next-intl
 * (messages/en.json), not a literal string, enforced by the
 * no-raw-jsx-text lint rule in eslint.config.mjs.
 */
export default async function TokensFoundationPage() {
  const t = await getTranslations("TokensFoundationPage");

  const swatches: Array<{ label: string; className: string }> = [
    { label: "surface", className: "bg-surface border border-border" },
    {
      label: "surface-raised",
      className: "bg-surface-raised border border-border",
    },
    { label: "brand", className: "bg-brand text-brand-ink" },
    { label: "danger", className: "bg-danger text-white" },
    { label: "success", className: "bg-success text-white" },
    { label: "warning", className: "bg-warning text-white" },
  ];

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 p-8">
      <header className="flex items-center gap-2">
        <Sparkles aria-hidden="true" className="text-brand" />
        <h1 className="text-2xl font-semibold text-ink">
          {productConfig.productName}
        </h1>
      </header>
      <p className="text-base text-ink-muted">{productConfig.tagline}</p>
      <p className="text-sm text-ink-muted">{t("caption")}</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {swatches.map((swatch) => (
          <div
            key={swatch.label}
            className={cn(
              "rounded-md p-4 text-sm font-medium",
              swatch.className,
            )}
          >
            {swatch.label}
          </div>
        ))}
      </div>
    </main>
  );
}
