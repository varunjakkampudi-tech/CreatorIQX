# ADR 0004: Separate Google OIDC login from the YouTube OAuth connection

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-08 |
| Deciders | Owner (Varun), coding agent |
| Spec reference | `CLAUDE.md` §4 feature 1, §10 (Authentication, YouTube connection, Logging), §3 (capability scopes) |

## Context

Users sign in with Google, and the app also needs Google OAuth access to their YouTube channel. Mixing the two would mean every login asks for YouTube permissions, a login session would hold channel-level power, and a user could not use the app (or disconnect YouTube) without affecting sign-in. YouTube write scopes are sensitive and must be requested only when a capability that needs them is enabled (ADR 0007). The owner confirmed on 2026-10-08 that login uses its own client (OQ-14).

## Decision

1. **Two independent flows, two OAuth clients** in the same Google Cloud project:

| Flow | Client | Scopes | Result |
|---|---|---|---|
| Login | Login-only web client | `openid email profile` only | A server-side session; no Google tokens are stored |
| YouTube connection | YouTube web client | Read-only first; write scopes per capability, only when enabled; upload scope only if `direct_video_upload` is enabled | Encrypted refresh token in `oauth_connections`, owned by the workspace |

2. **Login:** authorization code flow with PKCE, `state` and `nonce`; full ID token validation (issuer, audience, expiry, nonce, signature via Google's JWKS); `email_verified` required; v1 restricts login to an email allow-list. Server-side session in Redis with an opaque id in an HttpOnly, Secure, SameSite cookie, rotated on login.
3. **YouTube connection** (Phase 1A): a separate consent screen triggered from Settings or onboarding, with **incremental authorization**. Tokens encrypted at rest (AES-256-GCM, envelope encryption, key id for rotation), never logged; token lifecycle events (`youtube.token.used`, `refreshed`, `revoked`) go to the audit log without values. Disconnect revokes the token at Google and deletes it locally.
4. A user can log in, and keep using non-YouTube features, without any YouTube connection.
5. Client secrets live only in environment variables or a secrets manager, never in the repo, the Project docs or logs. A secret exposed anywhere else is rotated before use (OQ-15).

## Consequences

| Type | Consequence |
|---|---|
| Positive | Least privilege: login sessions never carry channel access; scopes grow only with enabled capabilities |
| Positive | Disconnecting YouTube never logs anyone out; login works when the YouTube connection is broken or expired |
| Negative | Two clients and two consent screens to configure; the creator sees two Google prompts during onboarding |
| Follow-up | P0-050 to P0-052 (login); Phase 1A (YouTube connection); owner creates the login client before P0-052 |

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| One client, login requests YouTube scopes | Every login asks for channel access; login session holds channel power; violates spec §10 |
| One client, two flows (login with identity scopes, connection with YouTube scopes) | Workable, but couples redirect URIs, consent configuration and secret rotation of a sensitive client to sign-in; rejected by the owner in favor of separation |
| Email and password accounts | More attack surface (password storage, resets) with no benefit for Google-based creators |

## Enforcement

- Test: the login authorization URL contains exactly `openid email profile`.
- Test: no Google access or refresh token is persisted by the login flow.
- Tests from P0-050 for state, nonce, audience, expiry, `email_verified` and the allow-list.
- Log-redaction test (P0-031): tokens never appear in logs.
