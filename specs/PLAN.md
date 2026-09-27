# Implementation Plan: Universal System-Adapter Kit

**As of:** 2026-09-27

This plan is derived from `specs/PRD.md` and `specs/HLD.md`. It orders the work and defines when each piece counts as done. It is not a source of truth: if this plan and a spec disagree, the spec wins and this plan gets fixed. Every task names the FR/NFR it serves so each PR can reference it, per `AGENTS.md`.

## How work flows

Each phase runs the same loop:

1. **Spec check.** Confirm the phase's open decisions (below) are resolved in `HLD.md`. If not, update the spec first, in its own PR.
2. **Tests first.** Write the tests that encode the phase's exit criteria. They fail.
3. **Build** until they pass. Nothing outside the phase's listed files changes.
4. **Reconcile.** If the code had to diverge from the spec, update the spec in the same PR.
5. **Gate.** CI green (`docker compose up` + full `pytest`), PR description cites FR/NFR ids.

## Status

| Phase | Scope                                             | PRD week | Status           |
| ----- | ------------------------------------------------- | -------- | ---------------- |
| 0     | Scaffold, Adapter contract                        | 1        | Done (`5359d24`) |
| 1     | Resolve spec gaps                                 | 1        | Not started      |
| 2     | CI, Registry, observability                       | 1        | Not started      |
| 3     | CRM: REST mock, API key auth, adapter, agent loop | 1        | Not started      |
| 4     | Ticketing: SQL mock, basic auth, adapter          | 2        | Not started      |
| 5     | Inventory: SOAP mock, OAuth2 CC, adapter          | 3        | Not started      |
| 6     | Full demo task end to end                         | 4        | Not started      |
| 7     | Portfolio deliverables                            | 4        | Not started      |
| 8     | Extensibility proof (fourth backend)              | post-v1  | Not started      |

## Phase 1: Resolve spec gaps

The specs leave these open or contradict each other. Each changes the design, so each is decided and written into `HLD.md` before code depends on it. Proposed defaults are given so the decision is a yes/no, not a blank page.

| #   | Gap                                                                                                                                                                                                                                                               | Where                                            | Proposed default                                                                                                                                                                                                    |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| G1  | **Adapter granularity.** The contract has one `execute()` per adapter and the diagram shows one adapter per backend, but FR4 requires 4+ operations per backend and the sequence diagram calls operation-level tools (`get_customer_ticket`, `check_part_stock`). | HLD Adapter Contract, Request Flow; PRD FR1, FR4 | One adapter per backend. `input_schema` has a required `operation` enum plus per-operation args. One tool per backend keeps FR6 (one class + one config entry) true.                                                |
| G2  | **Who calls the Auth Layer.** The sequence diagram has the adapter calling `Auth.resolve`, but `execute(input, credentials)` receives credentials already resolved.                                                                                               | HLD Request Flow vs Adapter Contract             | Registry calls `auth.resolve(adapter.auth_config)` and passes the result into `execute()`. Adapter authors never touch auth (FR3). Fix the diagram.                                                                 |
| G3  | **Ticketing transport.** PRD and HLD say "direct SQL / direct DB access", but the repo layout says "FastAPI + SQLite" and the quirks table gives it HTTP basic auth and 429 responses, which are HTTP concepts.                                                   | PRD Demo Plan; HLD Mock Backends, Repo Layout    | Keep it HTTP: FastAPI service exposing a SQL query endpoint over SQLite, basic auth, 429s. The adapter speaks SQL (parameterized) through that endpoint. Reword "direct SQL" to "SQL-backed".                       |
| G4  | **`Credentials` shape.** Undefined; currently a `dict[str, str]` placeholder in `core/adapter.py`.                                                                                                                                                                | HLD Adapter Contract                             | Request headers (`dict[str, str]`). Holds for all three schemes once G3 is HTTP. Move the type to `core/auth.py`.                                                                                                   |
| G5  | **Registry config format and how an entry names its adapter.** FR2/FR6 need a config file; format and contents are unspecified.                                                                                                                                   | PRD FR2, FR6; HLD Extensibility                  | TOML via stdlib `tomllib` (no new dependency). Each entry: `class = "adapters.crm:CrmAdapter"`, `base_url`, and the auth config table. Registry imports by dotted path, so a new backend never edits `registry.py`. |
| G6  | **How an adapter gets its `base_url`.** The contract has no constructor or settings.                                                                                                                                                                              | HLD Adapter Contract                             | Registry instantiates the class with the config entry's non-auth keys as kwargs.                                                                                                                                    |
| G7  | **OAuth2 token endpoint host.** `oauth2_cc` needs a `token_url`; no mock provides one.                                                                                                                                                                            | HLD Auth Translation, Mock Backends              | Inventory mock serves `POST /oauth/token` alongside its SOAP endpoint. Short token TTL so refresh-on-expiry is actually exercised.                                                                                  |
| G8  | **SOAP library.** "Spyne or zeep-server". Spyne's Python 3.12 support is uncertain and zeep is a client, not a server.                                                                                                                                            | HLD Tech Stack                                   | Verify Spyne on 3.12 in a spike. Fallback: FastAPI + stdlib `xml.etree` for the mock, `zeep` or stdlib for the adapter. Record the choice in HLD.                                                                   |
| G9  | **LLM provider and model.** "The provider SDK directly", no provider named.                                                                                                                                                                                       | HLD Tech Stack                                   | Anthropic Python SDK, model id in an env var. CI never calls it (see Phase 2).                                                                                                                                      |
| G10 | **Where quirks live.** HLD gives pagination to CRM, field naming to Inventory, rate limits to Ticketing. PRD week 3 says quirks go into "all three mocks".                                                                                                        | PRD Milestones vs HLD Mock Backends              | Follow HLD: one headline quirk per mock, plus inconsistent field naming across all three (it is inherent). Update PRD milestone wording.                                                                            |
| G11 | **Adapter READMEs vs "one file".** NFR Documentation wants a README per adapter; FR6 says a new backend is one class + one config entry, "no other file changes".                                                                                                 | PRD NFRs vs FR6                                  | The adapter module docstring is its README (auth requirements + operations). No extra file.                                                                                                                         |
| G12 | **Python version.** Spec says 3.12; the dev machine has 3.11.                                                                                                                                                                                                     | HLD Tech Stack                                   | Keep 3.12. Install it locally; CI pins 3.12.                                                                                                                                                                        |

**Exit:** every row above is decided and `HLD.md` (and `PRD.md` where noted) updated in one spec-only PR. This plan's table is then replaced by links to the updated sections.

## Phase 2: CI, Registry, observability

Built before any backend so every later phase lands behind a working gate.

| Task                                                                                                                                                                                                                                            | Serves                 | Files                               |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- | ----------------------------------- |
| GitHub Actions: Python 3.12, `pip install -e ".[dev]"`, `docker compose up -d`, `pytest`, then `pytest tests/integration`                                                                                                                       | HLD Testing & CI       | `.github/workflows/ci.yml`          |
| CI check: every module in `adapters/` has a matching `tests/test_<name>.py`, else fail                                                                                                                                                          | AGENTS.md Testing      | small script run in CI              |
| `core/registry.py`: load TOML config, import adapter classes by path, expose tool schemas, route a call by tool name                                                                                                                            | FR2, FR6               | `core/registry.py`, `adapters.toml` |
| Registry wraps every `execute()`: log system, operation, latency, success/failure; convert any exception that escapes an adapter into a failed `AdapterResult` as a last line of defense (and log it loudly, since it is a bug in that adapter) | NFR Observability, FR7 | `core/registry.py`                  |
| `core/auth.py` skeleton: `SecretResolver` (env vars), `resolve(auth_config) -> Credentials` with an explicit error for unknown scheme                                                                                                           | FR3                    | `core/auth.py`                      |

**Tests (fake adapters, no mocks):** registry loads N configured adapters; routes to the right one; unknown tool gives a structured error; an adapter raising still yields `AdapterResult(success=False)`; each call emits one log record with the four fields; missing env secret fails loudly naming the `secret_ref`.

**Exit:** CI runs on PRs and is green; `docker compose up` works with zero services or the first one.

## Phase 3: CRM (REST) + agent loop

| Task                                                                                                                                                    | Serves               | Files                                      |
| ------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- | ------------------------------------------ |
| CRM mock: FastAPI, customers / contacts / tickets, synthetic seed data, cursor pagination on list endpoints, API key check, 4+ operations               | FR4                  | `mocks/crm_service/`, `docker-compose.yml` |
| API key scheme in `auth.py`                                                                                                                             | FR3                  | `core/auth.py`                             |
| `adapters/crm.py`: operations list/get/create/update; follows cursors so the agent never sees pagination; maps HTTP and parse errors to `AdapterResult` | FR1, FR4, FR7        | `adapters/crm.py`, `adapters.toml`         |
| `agent/runtime.py`: plain tool-calling loop over registry tools, LLM client injectable so tests can script it                                           | FR5, NFR Testability | `agent/runtime.py`                         |

**Tests:** `tests/test_crm.py` against the running mock (pagination is exhausted; bad key gives structured error; 404 gives structured error). `tests/test_runtime.py` with a scripted fake LLM: the loop calls the tools in order, feeds results back, stops on final answer, surfaces a failed `AdapterResult` to the model rather than raising.

**Exit:** a live run with the real LLM completes a CRM-only task (manual, not in CI).

## Phase 4: Ticketing (SQL-backed)

| Task                                                                                                                                                            | Serves        | Files                                            |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- | ------------------------------------------------ |
| Ticketing mock: FastAPI + SQLite, tickets with status and assignment, seed data, basic auth, simulated 429 on a deterministic schedule (so tests are not flaky) | FR4           | `mocks/ticketing_service/`, `docker-compose.yml` |
| Basic auth scheme in `auth.py`                                                                                                                                  | FR3           | `core/auth.py`                                   |
| `adapters/ticketing.py`: 4+ operations, parameterized SQL only, 429 handling (bounded retry, then structured error)                                             | FR1, FR4, FR7 | `adapters/ticketing.py`, `adapters.toml`         |

**Tests:** `tests/test_ticketing.py`: each operation; wrong password; 429 then success; 429 exhausts retries gives structured error; an injection-shaped input is treated as data.

**Exit:** no changes to `registry.py`, `runtime.py`, or `adapters/crm.py` were needed. If they were, stop and revisit the contract (HLD Extensibility).

## Phase 5: Inventory (SOAP)

| Task                                                                                                                        | Serves        | Files                                            |
| --------------------------------------------------------------------------------------------------------------------------- | ------------- | ------------------------------------------------ |
| Inventory mock (library per G8): parts, stock levels, warehouse locations, `partNumber`-style naming, token endpoint per G7 | FR4           | `mocks/inventory_service/`, `docker-compose.yml` |
| OAuth2 client-credentials in `auth.py`: fetch, cache, refresh on expiry                                                     | FR3           | `core/auth.py`                                   |
| `adapters/inventory.py`: 4+ operations, XML to dict, SOAP faults and malformed XML to `AdapterResult`                       | FR1, FR4, FR7 | `adapters/inventory.py`, `adapters.toml`         |

**Tests:** `tests/test_inventory.py`: each operation; SOAP fault; malformed XML; token cached across calls; token refreshed after expiry; bad client secret.

**Exit:** same no-shared-changes check as Phase 4. Auth layer now covers all three schemes (Goal 3).

## Phase 6: Full demo task

| Task                                                                                                                                                               | Serves                 | Files                |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------- | -------------------- |
| Seed data across the three mocks that links up: a customer with an open ticket that references a part with stock                                                   | Demo Plan              | mock seed files      |
| Demo entry point: "find this customer's open ticket, check inventory for the part it references, update the customer's contact info"                               | FR5, Goal 1            | `agent/`             |
| Integration test: scripted fake LLM drives the full task against the three live mocks; asserts the final CRM record changed and the log has one line per tool call | FR5, NFR Observability | `tests/integration/` |

**Exit:** integration test green in CI; one manual run with the real LLM succeeds; `git diff` shows `agent/runtime.py` contains no backend names (Goal 1: agent unmodified).

## Phase 7: Portfolio deliverables

- `README.md`: what it is, quickstart, architecture diagram (reuse the HLD mermaid), how to add a backend.
- Adapter module docstrings complete per G11 (auth requirements + operations).
- 3-minute demo video: code (agent unaware of backend type), live run, logs.
- PRD/HLD final pass so they match what was built.

Serves Goal 4, NFR Documentation.

## Phase 8: Extensibility proof

The number that proves "reusable primitive" (Goal 2, FR6, NFR Extensibility). Done after v1 ships, and timed.

1. Pick a fourth mock backend in an unrelated domain (e.g. a billing REST API).
2. Start a timer. Add: one mock, one adapter class, one config entry, one test file.
3. **Pass** if: under 4 hours, adapter under 150 lines, and `git diff --stat` touches nothing in `core/`, `agent/`, or existing `adapters/*.py`.
4. Record the time, line count, and diff stat in the README. A fail is a spec finding, not a special case (HLD Extensibility).

## Traceability

| Requirement                                   | Phase(s)                 |
| --------------------------------------------- | ------------------------ |
| FR1 Adapter interface                         | 0, 3, 4, 5               |
| FR2 Config-driven discovery                   | 2                        |
| FR3 Auth schemes                              | 2, 3, 4, 5               |
| FR4 Mocks, 4+ ops, standalone                 | 3, 4, 5                  |
| FR5 Multi-step cross-backend run with logging | 3, 6                     |
| FR6 One class + one config entry              | 2, 8                     |
| FR7 Structured errors                         | 2, 3, 4, 5               |
| NFR Extensibility                             | 4, 5 (checks), 8 (proof) |
| NFR Testability                               | every phase              |
| NFR Observability                             | 2, 6                     |
| NFR Documentation                             | 7                        |
| Goal 1 Cross-backend proof                    | 6                        |
| Goal 2 Extensibility proof                    | 8                        |
| Goal 3 Auth coverage                          | 5                        |
| Goal 4 Portfolio deliverable                  | 7                        |
