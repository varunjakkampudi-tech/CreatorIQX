"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { $api } from "@/lib/api";

/**
 * The signed-in session, fetched once per app-shell mount and shared via
 * context so every page under `(app)` can read the CSRF token (needed on
 * every mutating request, `platform/idempotency.py`'s sibling pattern for
 * identity - see `identity/api/dependencies.py`'s `CSRF_HEADER`) without
 * each page re-fetching `/api/v1/auth/session` itself.
 *
 * `GET /api/v1/auth/session` and `GET /api/v1/me` are both wired
 * unconditionally (identity/sessions are core, not YouTube-gated), so they
 * are safe to call from any screen regardless of which optional modules a
 * given deployment has enabled.
 */
interface SessionContextValue {
  isLoading: boolean;
  isSignedIn: boolean;
  csrfToken: string | undefined;
  email: string | undefined;
  workspaceId: string | undefined;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const sessionQuery = $api.useQuery("get", "/api/v1/auth/session", {
    retry: false,
  });

  const value = useMemo<SessionContextValue>(() => {
    const data = sessionQuery.data;
    return {
      isLoading: sessionQuery.isLoading,
      isSignedIn: Boolean(data),
      csrfToken: data?.csrf_token,
      email: data?.email,
      workspaceId: data?.workspace_id,
    };
  }, [sessionQuery.data, sessionQuery.isLoading]);

  return (
    <SessionContext.Provider value={value}>
      {children}
    </SessionContext.Provider>
  );
}

/** Reads the shared session. Must be called under `<SessionProvider>`. */
export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    throw new Error("useSession must be used within a SessionProvider");
  }
  return ctx;
}
