# Contributing to CreatorIQX

These rules come from `CLAUDE.md` §0 and §12. If anything here disagrees with the spec, the spec wins.

## Workflow

| Rule | Detail |
|---|---|
| Plan before code | Each phase starts with a plan; each ticket starts by re-reading its acceptance test |
| Small steps | One ticket per change where possible; tests ship with the code |
| Branching | Trunk-based on `main`; short-lived branches; small pull requests |
| Commits | [Conventional Commits](https://www.conventionalcommits.org/) such as `feat(identity): add OIDC callback`; reference the ticket ID in the body |
| Versions | Semantic versioning; every release noted in `CHANGELOG.md` |
| Decisions | Every significant decision gets an ADR in `docs/adr/` |
| Uncertainty | Unverified facts go to `docs/OPEN_QUESTIONS.md`; prefer official docs; take the conservative path when unsure |
| Session continuity | Read `docs/PROGRESS.md` first; update it last |

## Definition of Done

Code, passing tests, clean lint and type checks, updated docs, and a noted security consideration.

## Ticket outcomes

Every ticket closes as exactly one of:

| Outcome | Meaning |
|---|---|
| PASS | Implementation, tests, evidence, documentation and security consideration all exist |
| BLOCKED | An external dependency prevents completion; the evidence names it |
| FAIL | The requirement is not met |

Never report partial completion. A PASS without evidence is invalid.

## Secrets

Never commit secrets. Use a local `.env` (gitignored) and keep `.env.example` free of real values. Secret scanning runs in pre-commit and CI.

## Scope guardrails

No Kubernetes, Kafka, Elasticsearch, GraphQL, microservices, external workflow engines, event sourcing, per-module databases or vector databases without an approved ADR (spec §18).
