# ADR 0001: Build a modular monolith with hexagonal module boundaries

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-08 |
| Deciders | Owner (Varun), coding agent |
| Spec reference | `CLAUDE.md` §3 (Style, Modules), §12 (Structure), §13, §18 |

## Context

CreatorIQX is built by one developer with a coding agent, runs locally in v1 and on one VPS later, and must become multi-user in v2 without a redesign. It spans many concerns (identity, YouTube sync, content, AI tasks, analytics). Microservices would multiply deployment, observability and consistency work far beyond what one person can sustain, and the spec forbids them without an ADR. A single unstructured codebase would make the later split, and safe change, hard.

## Decision

1. **One deployable backend** (FastAPI), **one worker** (Celery), **one web app** (Next.js), **one MCP server**. They share one Python domain codebase; the worker and MCP server import the api package rather than duplicating logic.
2. The backend is split into **bounded-context modules** under `apps/api/src/creatoriqx_api/modules/<context>/`, using the context names in spec §3 (`identity`, `workspaces`, `youtube`, `content`, `transcripts`, `qa`, `publishing`, `jobs`, `audit`, `telemetry` and so on). Modules are added only when a ticket needs them.
3. Every module uses **hexagonal layers**:

| Layer | Contains | May import |
|---|---|---|
| `domain` | Entities, value objects, domain errors, ports (interfaces) | Standard library and other domain code of the same module only; no framework |
| `application` | Use cases orchestrating the domain through ports | Its own `domain` |
| `infrastructure` | Adapters: SQLAlchemy repositories, Redis, Celery, HTTP clients | Its own `domain` and `application`, frameworks |
| `api` | FastAPI routers, request and response schemas | Its own `application`; mapping only, no business logic |

4. **Each table has exactly one owning module.** Other modules use the owner's public application interface or domain events, never its tables or its `infrastructure` package.
5. Dependencies are wired by **dependency injection** at the composition root (app factory), so adapters are swappable in tests.

## Consequences

| Type | Consequence |
|---|---|
| Positive | One process to run, debug and deploy; simple transactions inside a module; clear seams to extract a module later |
| Positive | Domain logic is testable without databases or frameworks |
| Negative | Boundaries are by convention unless tooling enforces them; a shared database tempts cross-module queries |
| Negative | More files per feature than a flat layout |
| Follow-up | P0-011 import-linter contracts; P0-012 dependency-cruiser for the web app; P0-053 builds `workspaces` as the reference module |

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Microservices | Operational cost far beyond a one-person team; forbidden by spec §18 without a concrete need |
| Flat layered monolith (one `models`, one `services`, one `routes`) | No module boundaries; table ownership and later extraction become hard |
| Separate database per module | Forbidden by spec §18; loses simple transactions; no current need |

## Enforcement

- **import-linter** (CI and pre-commit): a `domain` package may not import FastAPI, SQLAlchemy, Celery, Redis or Pydantic-settings; no module may import another module's `infrastructure` or `api` package; `api` may not import `infrastructure` directly.
- **dependency-cruiser** for the web app's internal boundaries.
- Code review checks table ownership against `docs/DATA_MODEL.md`.
