# ADR 0005: Put all runtime AI behind an LLMProvider port, MCP bridge in v1

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-10-08 |
| Deciders | Owner (Varun), coding agent |
| Spec reference | `CLAUDE.md` §2 (AI budget, Build agent vs runtime AI provider, AI strategy), §9, §17 (AI quality, Budget) |

## Context

The v1 AI budget is a Claude Pro subscription only, and a subscription cannot be called as an API by the app. v2 will want per-use API calls. AI output is untrusted (it can hallucinate, and its inputs such as comments and transcripts can carry prompt injection), and no AI output may cause a public action without human approval. Changing providers must not mean rewriting features.

## Decision

1. Features depend only on an **`LLMProvider` port** in the `ai_gateway` module. Two adapters:

| Adapter | Mode | v1 status |
|---|---|---|
| `McpBridgeProvider` | Mode A: the app writes `ai_tasks`; the owner's Claude (Code or desktop) claims them through MCP tools, does the work, and submits results | **Default and only enabled mode** |
| `AnthropicApiProvider` | Mode B: direct API calls | Built behind a feature flag, tested with mocked calls, **disabled**. Enabling it for real use requires an owner ADR |

2. Mode B always runs under a **hard monthly spend cap** with warnings at 50%, 80% and 100% and automatic fallback to Mode A at the cap. There is no API mode without a cap.
3. **AI tasks are leased:** `claimed_by`, `claimed_at`, `lease_expires_at`; an abandoned task becomes claimable again. Tasks record `prompt_version`, `input_schema_version` and `output_schema_version`.
4. **Prompts are versioned files** with JSON-schema outputs; every output is validated with Pydantic and retried on invalid output.
5. **Untrusted input stays data:** comments, transcripts, titles and web content go into delimited data sections, never instructions. MCP tools are read-only by default; mutating tools only create drafts. **AI never triggers side effects;** drafts pass through the approval gate.
6. Model names come from configuration, never code.
7. Before any unattended processing loop, Anthropic's usage terms for automated use are verified and recorded (OQ-08). Until then, the owner starts each run.

## Consequences

| Type | Consequence |
|---|---|
| Positive | Zero API cost in v1; provider swap is configuration; one eval harness compares providers |
| Positive | The approval gate, not the model, decides what becomes public |
| Negative | Mode A needs the owner's Claude session running; tasks wait otherwise. The UI must make this visible ("waiting for Claude") |
| Negative | Two adapters to keep conformant |
| Follow-up | `ai_gateway` module (Phase 1A or 1C, when the first AI feature lands); shared adapter contract tests; prompt-injection test set |

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Call the Anthropic API directly from features | Violates the v1 budget; couples features to one vendor |
| Automate the Claude consumer app | Against terms of use and fragile; never an option |
| Local model only | Quality and hardware limits for the owner's use; can be added later as another adapter |

## Enforcement

- import-linter: only `ai_gateway.infrastructure` may import an AI SDK.
- Shared contract tests that both adapters must pass.
- A test proves Mode B cannot be enabled without a configured cap, and that the feature flag defaults to off.
- Prompt-injection test set: malicious comments and transcripts must produce zero side effects.
