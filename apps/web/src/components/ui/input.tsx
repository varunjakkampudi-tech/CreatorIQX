import { forwardRef } from "react";
import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export type InputProps = InputHTMLAttributes<HTMLInputElement>;

/**
 * The design-system Input (P0-083). `aria-invalid` (set by the caller, not
 * this component - it doesn't know the validation rule) drives the error
 * color through a token, never a separate hard-coded "error" variant.
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      className={cn(
        "w-full rounded-md border border-border bg-surface px-4 py-2 text-base text-ink placeholder:text-ink-muted",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
        "aria-invalid:border-danger aria-invalid:focus-visible:ring-danger",
        "disabled:pointer-events-none disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
});
