import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export type SkeletonProps = HTMLAttributes<HTMLDivElement>;

/**
 * The design-system Skeleton (P0-083): a pulsing loading placeholder.
 * `aria-hidden` because a skeleton has no content to announce - the
 * surrounding UI is responsible for its own loading announcement (e.g. an
 * `aria-busy` region or a visually-hidden "Loading..." label), so this
 * component never reads as an empty, unlabeled element to a screen reader
 * (the axe check in P0-083's acceptance test would otherwise flag exactly
 * that). `animate-pulse` already respects `prefers-reduced-motion`
 * (globals.css forces every animation/transition duration to ~0 under it).
 */
export function Skeleton({ className, ...props }: SkeletonProps) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "animate-pulse rounded-md bg-border",
        className,
      )}
      {...props}
    />
  );
}
