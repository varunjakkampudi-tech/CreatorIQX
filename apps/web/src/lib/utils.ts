import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge class names, resolving conflicting Tailwind utilities (the shadcn/ui
 * convention). Every component composes classes through this helper instead
 * of string-concatenating class names.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
