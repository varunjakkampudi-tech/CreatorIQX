import type { ReactNode } from "react";
import { SessionProvider } from "@/lib/session-context";
import { AppShell } from "@/components/app-shell";

/**
 * Shared shell for every product screen (spec section 11: Dashboard,
 * Content, Settings, ...). `(app)` is a route group - it groups these
 * routes under one layout without adding a `/app` segment to the URL.
 */
export default function AppGroupLayout({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <AppShell>{children}</AppShell>
    </SessionProvider>
  );
}
