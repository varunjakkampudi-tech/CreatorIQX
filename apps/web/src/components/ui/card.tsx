import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export type CardProps = HTMLAttributes<HTMLDivElement>;

/**
 * The design-system Card (P0-083): a bordered, raised surface container.
 * Deliberately minimal (no Header/Content/Footer split) - callers compose
 * their own layout inside with the spacing-grid utilities (p-4, gap-2, ...).
 */
export function Card({ className, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-lg border border-border bg-surface-raised p-4",
        className,
      )}
      {...props}
    />
  );
}
