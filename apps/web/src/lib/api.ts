import { createApiClient } from "@creatoriqx/api-client";
import createQueryHooks from "openapi-react-query";

/**
 * `/api` is rewritten to the local FastAPI backend by next.config.ts
 * (P0-080), so the browser never needs the backend's real origin.
 */
const fetchClient = createApiClient({ baseUrl: "/api" });

/**
 * Typed TanStack Query hooks over the fetch client. `paths` comes from
 * packages/api-client's generated schema.d.ts: a change to an endpoint's
 * request or response shape in the API changes this file's types, and a
 * caller that still expects the old shape fails to compile - the
 * acceptance test this ticket (P0-081) is built around.
 */
export const $api = createQueryHooks(fetchClient);

/**
 * Proves the generated client is actually load-bearing (P0-081's
 * acceptance test): a typed call to /api/v1/me that compiles today, and
 * would fail to compile the moment that endpoint's response shape
 * changes in the API without this hook being updated to match. Not used
 * by any page yet - frontend screens wait on P0-090 - but `tsc --noEmit`
 * and `next build` both type-check it regardless.
 */
export function useCurrentUser() {
  return $api.useQuery("get", "/api/v1/me");
}
