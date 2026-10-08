# CreatorIQX Testing

> **Status: stub.** Filled as test layers land, starting with P0-011 and P0-100.

## Purpose

The test strategy: unit, integration (real PostgreSQL and Redis), contract (OpenAPI drift), security (cross-tenant harness, RLS meta-test, log redaction), end-to-end (Playwright plus axe), coverage gates (85% domain and application, 70% overall), and how to run each locally and in CI (spec §12, §17).
