"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

/**
 * One QueryClient per browser session (not per render), created inside
 * useState so React Strict Mode's double-render doesn't throw it away.
 * Server Components can't hold client-side cache state, so this is the
 * client boundary layout.tsx wraps every page in.
 */
export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
