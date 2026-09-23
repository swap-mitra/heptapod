# Universal System-Adapter Kit — PRD

**As of:** 2026-09-23

## Overview

The Universal System-Adapter Kit is a small Python library that gives an LLM agent one uniform tool interface for calling into any backend system, a REST API, a SOAP service, or a SQL database, with authentication translated underneath so the agent code never changes per system. v1 proves this against three unrelated mock backends (a CRM-style REST API, a SOAP-style inventory service, and a SQL-backed ticketing system) so the same agent completes a task across all three unmodified.

This is the flagship artifact for a forward deployed engineer (FDE) portfolio: it is a working version of the "reusable primitive" that the FDE model is actually built on, customer-facing engineers building customized solutions on top of a shared platform rather than one-off integrations per client ([Anthropic / ZenML](https://www.zenml.io/llmops-database/forward-deployed-engineering-for-agentic-ai-platforms)).

## Goals & Success Metrics

1. **Cross-backend proof**: one agent, unmodified, completes a multi-step task that spans all three mock backends (e.g. "find this customer's open ticket, check inventory for the part it references, update their contact record") using only the adapter layer.
2. **Extensibility proof**: adding a fourth mock backend after v1 takes under 4 hours and under 150 lines of adapter code, with zero changes to the agent or the other adapters. This is the number that actually proves "reusable primitive" rather than "worked once."
3. **Auth coverage**: the auth translation layer handles at least three schemes (API key, OAuth2 client-credentials, basic auth) behind the same interface.
4. **Portfolio deliverable**: a public repo with README, architecture diagram, a 3-minute demo video, and this PRD/HLD, positioned as the artifact for FDE interviews.

## Problem Statement

Enterprise AI pilots overwhelmingly fail to reach production or deliver measurable value. MIT's Project NANDA found 95% of generative AI pilots show no measurable P&L impact, and independent research points to a small set of predictable, recurring failure points rather than model quality: data mismatch between clean pilot data and messy production data, no edge-case handling, no monitoring once live, integration gaps, and no adoption plan ([RaftLabs](https://www.raftlabs.com/blog/ai-pilot-to-production)).

Integration is the single largest and earliest of these. Roughly 95% of agent pilots stall specifically because enterprise systems span decades of different authentication models with no unified access layer, and that connective plumbing is usually scoped out of the pilot to keep it moving, then discovered too late ([Viviscape](https://viviscape.com/news/agent-pilot-graveyard-enterprise-ai-2026)).

There is no small, reusable way to give an agent a uniform interface to arbitrary backend systems while keeping each system's real auth model intact. Every integration gets built bespoke, per client, which is exactly the gap this project closes.

## Target Users

| User | Need |
| --- | --- |
| FDE embedded at a customer | Wire an agent into 3-5 existing systems fast, without one-off integration code per system |
| Platform team | Standardize how internal agents talk to internal services behind one contract |
| Interviewer / hiring panel | See a working, generalized version of the exact primitive the FDE role is built around, not a single-domain demo |

## Scope

**In scope (v1)**

- A Python adapter interface (protocol/ABC): name, description, input schema, auth config, `execute()`.
- Three mock backends built into the repo: REST API, SOAP service, SQL-backed service, each with realistic quirks (pagination, inconsistent field naming, rate limits), not clean toy data.
- An auth translation layer covering API key, OAuth2 client-credentials, and basic auth behind one config shape.
- A stub agent (single LLM tool-calling loop) that uses the adapters to complete a multi-step task.
- Config-driven registration: a new system is one adapter class plus one config entry, with no change to the agent.

**Out of scope (v1)**

- Production-grade secrets management (env vars / a local vault stub only).
- Streaming or websocket backends.
- Multi-tenant credential isolation.
- Any UI for adapter configuration (CLI/config file only).

## Functional Requirements

| ID | Requirement |
| --- | --- |
| FR1 | The system exposes one `Adapter` interface that any backend implementation satisfies: `name`, `description`, `input_schema`, `auth_config`, `execute(input) -> output` |
| FR2 | An agent discovers available adapters from a config file at startup, with no hard-coded per-system logic in the agent |
| FR3 | The auth layer accepts API key, OAuth2 client-credentials, and basic auth configs, and injects credentials per-request without the adapter author writing auth code |
| FR4 | Each of the three mock backends is runnable standalone (`docker compose up`) and exposes at least 4 operations (e.g. list, get, create, update) |
| FR5 | The agent completes a scripted multi-step task spanning all three backends in one run, logging each tool call and its result |
| FR6 | Adding a new backend requires writing one adapter class and one config entry only; no other file changes |
| FR7 | A failed or malformed backend response surfaces as a structured error to the agent, not a raw exception |

## Non-Functional Requirements

- **Extensibility**: a new adapter is under 150 lines and needs no changes outside its own file plus one config entry (this is the number Goal 2 measures against).
- **Testability**: every adapter has unit tests against its mock backend, independent of the LLM; the agent loop is tested separately with a scripted tool-call sequence so correctness does not depend on model output.
- **Observability**: every tool call logs system name, operation, latency, and success/failure, so a failure is traceable to one adapter without reading agent transcripts.
- **Documentation**: each adapter's README states its auth requirements and the operations it exposes, written as if a new engineer will pick it up cold.

## Demo Plan

Three mock backends, deliberately unrelated domains so the "portable primitive" claim is provable, not asserted:

1. **CRM-style REST API** — customer records, contact info, open tickets.
2. **SOAP-style inventory service** — parts, stock levels, warehouse locations.
3. **SQL-backed ticketing system** — support tickets, status, assignment.

**Demo script**: the agent runs one task end to end, "find this customer's open ticket, check inventory for the part it references, and update the customer's contact info," touching all three systems through the same adapter interface with no per-system logic in the agent. A 3-minute recording walks through the code (agent unaware of backend type), the live run, and the logs showing each adapter call.

**What it proves**: the adapter contract generalizes across REST, SOAP, and direct DB access, and across three unrelated business domains, which is the specific claim an FDE role needs demonstrated.

## Risks & Open Questions

| Risk / Question | Notes |
| --- | --- |
| Mocks read as too clean to be convincing | Deliberately add real-world quirks: pagination, inconsistent field naming across systems, occasional rate-limit responses |
| Scope creep toward supporting every protocol (GraphQL, gRPC, message queues) | Hard cap v1 at three backend types; note the rest as future work, don't build them |
| Should auth config be pluggable at runtime or fixed at adapter-definition time? | Default to fixed at definition time for v1; runtime pluggability is a stretch goal only if time allows |
| Is a single LLM tool-calling loop enough, or does the demo need a heavier orchestration framework? | Start with a plain tool-calling loop (no framework); only reach for one if the demo task genuinely needs multi-turn planning |

## Milestones & Timeline

Scoped for evenings/weekends alongside full-time work, roughly 4 weeks:

| Week | Milestone |
| --- | --- |
| 1 | Adapter interface defined; REST mock backend built; basic agent tool-calling loop works end to end against it |
| 2 | SQL-backed mock backend added; auth translation for API key and basic auth working across both adapters |
| 3 | SOAP mock backend added; OAuth2 client-credentials support; config-driven registration in place; quirks (pagination, rate limits) added to all three mocks |
| 4 | Full three-backend demo script working; logging/observability added; README, architecture diagram, 3-minute demo video, and this PRD/HLD finalized; repo published |
