# ADR 0010: Use server-side sessions in Redis with CSRF tokens and two timeouts

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-09 |
| Deciders | Owner (Varun), coding agent |
| Spec reference | `CLAUDE.md` A10 (Authentication, session security), A4 feature 1; ADR 0004 (login flow) |

## Context

ADR 0004 requires a server-side session after Google login. The first implementation used Starlette's signed-cookie `SessionMiddleware`. That design cannot meet the requirements in A10:

- Logout cannot invalidate a cookie that is still signed and unexpired, so a stolen cookie stays valid until it ages out.
- Idle and absolute timeouts cannot be enforced server-side.
- Session rotation on login (anti-fixation) has no server record to rotate.
- Every worker must share the same signing secret, and rotating it signs everyone out.

The app already runs Redis for quota, rate limits and the job broker (ADR 0003, ADR 0009), so sessions add no new infrastructure.

## Decision

1. **Opaque server-side sessions.** The browser holds a random 256-bit identifier (`secrets.token_urlsafe(32)`). The record (user subject, email, CSRF token, timestamps) lives in Redis under `session:<id>`. The cookie reveals nothing about the user.
2. **Two timeouts.** The idle timeout (default 60 minutes, configurable) ends a session after inactivity and restarts on every authenticated request. The absolute timeout (default 12 hours) ends it regardless of activity. Redis expires the record at the absolute deadline; the application enforces the idle deadline on every read.
3. **Rotation on login.** Every successful login creates a new session id and deletes the previous one from the cookie, so an id planted before login is useless.
4. **CSRF synchroniser token.** Each session carries a CSRF token, returned by `GET /api/v1/auth/session`. Unsafe requests must send it in `X-CSRF-Token`. The comparison is constant-time, and missing or non-ASCII values are rejected. Cookies are `SameSite=Lax`, so the header is a second, independent barrier.
5. **Cookie attributes, always.** `__Host-` name prefix, `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`. The prefix stops a sibling host or path from planting a cookie that shadows the real one. Browsers treat `http://localhost` as a secure context, so local development uses the same attributes; OQ-10 tracks per-browser confirmation.
6. **Single-use login flow.** The OIDC `state`, `nonce` and PKCE verifier are stored server-side under a short-lived flow id (default 10 minutes). The callback consumes them with an atomic `GETDEL`, so a replayed callback finds nothing.
7. **Ports and adapters.** `SessionService` depends on a `KeyValueStore` port, implemented by Redis in production and by an in-memory store in tests. The clock is injected, so timeout rules are tested without sleeping.
8. **Logout** ends the session server-side (the id stops working at once), clears the cookie, and requires the CSRF header.

## Consequences

| Type | Consequence |
|---|---|
| Positive | Logout and expiry take effect immediately on every worker |
| Positive | No signing secret to share or rotate; a Redis flush signs everyone out, which is the expected behaviour |
| Positive | Session state can be inspected and revoked by an operator (later: an admin "sign out everywhere") |
| Negative | Every authenticated request costs one Redis round trip. Accepted: Redis is already on the request path for readiness and quota |
| Negative | Redis is now a hard dependency for sign-in. Readiness checks it (P0-030); production requires Redis auth (SECURITY.md accepted risks) |
| Follow-up | P0-052 (real login check), P0-053 (workspace bootstrap uses the session subject), P0-054 (RBAC on `current_session`), P0-055 (rate limits on `/auth/login` and `/auth/callback`) |

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Signed or encrypted stateless cookies (Starlette `SessionMiddleware`, JWT in a cookie) | Cannot be revoked before expiry, cannot enforce idle timeouts, and needs a shared secret; rejected |
| JWT access tokens in `localStorage` | Readable by any script (XSS); no revocation; rejected |
| Database-backed sessions in PostgreSQL | Works, but adds a write on every request and a second source of truth for expiry; Redis already exists and is built for this |
| Third-party auth provider (Auth0, Clerk) | Adds a vendor and a second identity store; the owner chose Google login with the app owning sessions (ADR 0004) |

## Enforcement

- `apps/api/tests/test_sessions.py`: idle timeout, activity restarts the idle timer, activity never extends the absolute lifetime, expired records are removed, rotation invalidates the old id, CSRF rejects missing, wrong and non-ASCII tokens.
- `apps/api/tests/test_session_routes.py`: 401 without a cookie, `no-store` on the session response, logout needs the CSRF header, logout clears the cookie, idle expiry is reported as `session-expired`.
- `apps/api/tests/test_auth.py`: the callback sets the session cookie with `HttpOnly` and `SameSite=Lax`, clears the flow cookie, and redirects; replayed or missing flows fail.
- `tests/integration/test_session_store_redis.py`: two service instances share one Redis session; Redis holds the absolute TTL; flow records are single-use.
- Log redaction (P0-031) keeps session ids and CSRF tokens out of logs; the login log records only the subject.
