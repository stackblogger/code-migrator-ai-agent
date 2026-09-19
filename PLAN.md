# AI Code Migration Agent — Build Spec (v2)

You are a senior AI systems architect, compiler engineer, and developer-tools engineer.
Build a production-oriented **AI Code Migration Agent** that migrates a repository from a
supported source language/framework to a supported target language/framework, and **proves**
that the migrated system behaves like the original.

This is not a "translate this file" wrapper. It is an evidence-driven migration system.

---

## 0. The Prime Directive: No Silent Failure

"Fail-proof" does not mean the LLM never makes mistakes. It means:

1. **Every source behavior is accounted for.** Each one is either *proven equivalent*,
   *explicitly waived by a human*, or *reported as a gap*. Nothing disappears silently.
2. **Equivalence is measured against the running source system**, not against the LLM's
   understanding of it and not against tests the LLM translated itself.
3. **The agent cannot grade its own homework.** Validation artifacts are sealed and read-only
   to the agents that generate and fix code, and some of them are held out entirely.
4. **Completion is a set of gates backed by evidence.** Every gate links to artifacts
   (logs, trace diffs, reports). If a gate cannot be evaluated, the result is
   `INSUFFICIENT VALIDATION`, never `PASS`.
5. **The safety net ships with the result.** The behavioral harness becomes a permanent
   contract-test suite in the target repo, and the migration comes with a cutover and
   rollback kit.

Every design decision below serves these five rules.

---

## 1. Inputs

```yaml
source:
  repo: <local path | git url>
  language: typescript
  framework: nestjs
  orm: typeorm
  test_framework: jest
target:
  language: python
  framework: fastapi
  orm: sqlalchemy
  test_framework: pytest
requirements:            # optional free text + structured constraints
  - "Keep REST paths and JSON field names identical"
acceptance:              # user-defined gates; see §9
  differential_pass_rate: 1.0
  holdout_pass_rate: 1.0
  min_harness_mutation_score: 0.70
  min_source_coverage_by_harness: 0.80
  perf_p95_ratio_max: 1.5
  allow_waivers: true
```

Initial supported pairs: **TypeScript/NestJS ⇄ Python/FastAPI**. Other pairs (Java→Kotlin,
Go→Rust, and so on) are supported by adding adapters, not by changing the core engine.

---

## 2. Core Concepts

| Concept | Purpose |
|---|---|
| **Repository Inventory** | Languages, package managers, build and test tools, entry points, config, env vars, services. |
| **Code Graph** | Symbols, imports, calls, and framework metadata. Cycles are collapsed into strongly connected components (SCCs). |
| **Canonical Concept Model (CCM)** | A language-neutral model of architecture: `HttpRoute`, `DIProvider`, `OrmEntity`, `Validator`, `AuthGuard`, `Middleware`, `Job`, `ConfigKey`, `ErrorMapping`, `OutboundCall`, `LogEvent`. Framework adapters map *source→CCM* and *CCM→target*, so N frameworks need N adapters instead of N×M pairwise mappings. |
| **Behavior Baseline** | Golden traces recorded from the **running source system**: inputs, outputs, DB state changes, side effects. |
| **Traceability Ledger** | Every source item (endpoint, entity, field, config key, env var, error code, job, auth rule, log event) maps to a target item or to a waiver. |
| **Migration Unit** | The smallest thing that is migrated and validated as one (an SCC-collapsed group of symbols). |
| **Evidence** | Immutable artifacts attached to gates, such as test logs, trace diffs, and reports. |

---

## 3. Pipeline

```text
A. Discover & Analyze
      ↓
B. Capture Source Baseline      ← BEFORE any code is migrated
      ↓
C. Plan (SCCs, interface-first, risk-ranked)
      ↓
D. Target Skeleton (compiles, all signatures + stubs)
      ↓
E. Unit Migration Loop  (migrate → build → unit test → differential test → fix)
      ↓
F. Integration & Full Differential Validation
      ↓
G. Hardening (hazards, property/fuzz, authz matrix, mutation, perf, hold-out)
      ↓
H. Adversarial Review + Human Sign-off
      ↓
I. Cutover Kit (shadow, canary, rollback, permanent contract tests)
```

The state machine is persisted: `DISCOVERING → ANALYZING → BASELINING → PLANNING → READY →
MIGRATING ⇄ BUILDING ⇄ TESTING ⇄ FIXING → VALIDATING → HARDENING → REVIEW → COMPLETED`,
plus `PAUSED`, `BLOCKED`, `FAILED`, and `CANCELLED`. Per-unit states are tracked separately.

---

## 4. Phase B: Behavior Baseline (the heart of the system)

The **running source system is the oracle**. If the source cannot be built and run in the
sandbox, the migration is capped at `UNVERIFIED` and the report says so explicitly.

### 4.1 Language-neutral black-box harness

The harness is written once, in Python, and runs against both systems. It observes:

- **HTTP/CLI I/O**: status, selected headers, body, and exit codes
- **Database state**: a row-level diff of the DB before and after each request
- **Side effects**: outbound HTTP calls, queue messages, emails, and files written. These are
  captured through a record/replay proxy and fake brokers.
- **Error shape**: status code, error body schema, and error code
- **Structured log events** (optional, configurable)

### 4.2 Determinism controls (required before any comparison)

- Frozen or fake clock, fixed timezone (`UTC`), and fixed locale
- Seeded RNG and deterministic UUID/ID generation (injected, or normalized by rule)
- A fresh database from the same seed for every trace
- External services stubbed via record/replay
- **Self-consistency check**: replay the baseline against the *source* twice. Any trace that
  differs between two runs of the source is flagged as flaky. It is then either fixed with a
  normalization rule or excluded, with a recorded reason. A trace that is not stable against
  the source cannot be used to judge the target.

### 4.3 Where traces come from

1. The existing source test suite, instrumented to record traces at the system boundary
2. Route and schema enumeration (OpenAPI / framework metadata), with generated valid,
   invalid, and edge-case requests
3. Property-based and fuzz inputs (Hypothesis / Schemathesis style)
4. Hazard-targeted cases (§6)
5. Authorization matrix cases (§7.3)
6. Optional sampled production traffic, redacted, supplied by the user

### 4.4 Harness strength is measured, not assumed

- **Source coverage under the harness**: which source lines and branches the traces exercise
- **Mutation score on the source**: mutate the source code and check whether the harness
  notices. If mutants in module X survive, evidence for X is marked `WEAK`.
- Weakly covered units get extra generated traces *before* migration starts.
- If thresholds are not met, gate G0 fails and the report says `INSUFFICIENT VALIDATION`
  for those areas.

### 4.5 Sealed and hold-out traces

- All baseline traces and the harness are **read-only** to the migration and fix agents
  (enforced by tool permissions, not by prompt).
- **20% of traces are held out.** The generating and fixing agents never see them. They run
  only at gate G4. This catches code that was "fixed" to satisfy specific visible traces
  instead of implementing the behavior.
- Comparison **normalization rules** (for example "ignore `updatedAt` within 1s", or
  "ignore key order") are declared, versioned, and listed in the report. The LLM may *propose*
  a rule. A human must approve it. Every rule is a waiver.

---

## 5. Traceability Ledger

Built during analysis from static extraction and the CCM. Every row must end in exactly one
of: `MAPPED+VERIFIED`, `MAPPED+UNVERIFIED`, `WAIVED(reason, approver)`, `MISSING`.

It is checked with **static diffs** that do not depend on tests:

| Check | Method |
|---|---|
| API surface | Extract routes/OpenAPI from both → diff paths, methods, params, request/response schemas, status codes |
| DB schema | Run migrations on both sides against real DBs, introspect, diff tables, columns, types, nullability, indexes, constraints, defaults |
| Config / env | Diff the env vars and config keys each side reads, including defaults |
| Error catalog | Diff error codes/types and their HTTP mapping |
| Auth rules | Diff guard/decorator/dependency annotations per route |
| Jobs / queues / cron | Diff schedules, topics, and consumers |
| Dependencies | Every source dependency is mapped to a target equivalent (with license and vulnerability scan), or marked as intentionally removed |

Migration cannot reach `COMPLETED` while any ledger row is `MISSING`.

---

## 6. Semantic Hazard Catalog

Migrations usually break on subtle runtime differences, not on syntax. Each framework/language
adapter ships a **hazard checklist**. Each hazard has a detector (does this repo use the
construct?) and a test generator that produces targeted differential traces.

Minimum catalog:

- JSON field casing (camelCase ⇄ snake_case), `null` vs missing vs `undefined`, empty arrays
- Date/time: timezone, ISO format, precision (ms vs µs), DST
- Numbers: float vs decimal, integer overflow (JS `number` vs Python `int`), rounding modes,
  `NaN`/`Infinity` serialization
- Strings: Unicode normalization, case folding, byte vs char length, regex dialect differences
- Sorting and collation, stable sort, locale-aware comparison
- ORM: transaction boundaries, isolation level, autoflush/lazy loading, cascade rules,
  soft-delete, default values (DB-side vs app-side)
- Validation: coercion rules (`"1"` → `1`?), whitelist/strip unknown fields, error message shape
- Error mapping: uncaught exception → status code, error body format
- Async: ordering of concurrent operations, fire-and-forget promises, event-loop blocking,
  retries and timeouts on outbound calls
- Auth: token parsing, clock skew, case sensitivity of roles, and default-deny vs default-allow
- Pagination: off-by-one, default page size, cursor encoding
- Config: env var parsing (`"false"` truthiness), defaults when missing

---

## 7. Phase G: Hardening

### 7.1 Property-based and fuzz differential testing
Generate random valid and invalid inputs per route from the CCM schemas. Run them against both
systems and diff the results. Shrink any divergence to a minimal reproduction and file it as an issue.

### 7.2 Mutation testing on the target
Run mutation testing on the target code with the migrated test suite plus the contract suite.
It must meet the same threshold as the source, so the target's safety net is not weaker than
the original.

### 7.3 Authorization matrix
For every `endpoint × role/identity (anonymous, each role, wrong tenant, expired token)`,
record allow/deny on the source and replay on the target. **Any divergence blocks completion.
Waivers are not allowed** for security gates unless the user explicitly overrides with a reason.

### 7.4 Performance sanity
Replay the trace corpus under light load on both systems and compare p50/p95 latency and error
rate. This is not a benchmark. It exists to catch N+1 queries, sync-in-async blocking, and
missing indexes.

### 7.5 Anti-cheat static checks on the target
The build fails on any of the following:
- `TODO`, `FIXME`, `NotImplementedError`, stub bodies, `pass`-only functions in migrated units
- Skipped, xfail, or deleted tests; lowered assertion counts versus the source
- Broad `except:` / `catch {}` that swallows errors where the source did not
- Literals that match fixture/trace values in non-test code (hardcoded answers)
- Special-casing test environments (`if TESTING:` branches not present in source)

---

## 8. Migration Strategy (Phases C–E)

- **Plan units from SCCs** of the code graph, in topological order. Rank them by risk
  (fan-in, hazard count, weak evidence) so the riskiest units are validated early.
- **Interface-first skeleton**: generate every target module, type, signature, route, and
  entity with stub bodies first. The target must compile and start from day one. This enables
  parallel unit work and precise failure attribution.
- **Per-unit loop**:
  1. Assemble minimal context: source unit, its CCM nodes, dependency *interfaces* (not their
     bodies), related traces, and hazards.
  2. Generate the target implementation plus unit tests (structured output).
  3. Format → lint → type-check → build.
  4. Run unit tests, then differential traces scoped to this unit.
  5. On failure: attribute the failure to a unit (via the skeleton boundaries), diagnose, fix,
     and retry.
  6. `MAX_FIX_ATTEMPTS = 5` → `BLOCKED` with a diagnosis bundle for a human.
- **Git is the code state**: each unit attempt is a commit on a migration branch. Rolling back
  a unit means reverting its commits. The diff viewer reads from git.
- **Adversarial reviewer**: a separate agent (different prompt, ideally a different model)
  receives the source unit, the target unit, and the hazard list. Its only job is to find
  semantic differences. Each finding becomes a new differential trace, not just a comment.

---

## 9. Quality Gates

A migration is `COMPLETED` only when every enabled gate passes or is waived with an approver.
Each gate stores its evidence.

| Gate | Criterion |
|---|---|
| **G0 Baseline** | Source builds and runs in sandbox; traces are self-consistent; harness coverage and mutation score ≥ thresholds |
| **G1 Static** | Target compiles, strict type-check passes, lint clean, anti-cheat checks clean |
| **G2 Unit tests** | Migrated plus generated unit tests pass; none skipped |
| **G3 Differential** | Visible trace corpus passes at the configured rate (default 100%) |
| **G4 Hold-out** | Hold-out traces pass (default 100%) |
| **G5 Surface diffs** | API, DB schema, config, and error-catalog diffs are empty or waived |
| **G6 Ledger** | 0 `MISSING`; `MAPPED+UNVERIFIED` below the threshold |
| **G7 Hazards** | All detected hazards have passing targeted traces |
| **G8 Security** | Authz matrix identical; secrets scan clean; dependency vulnerability scan meets policy |
| **G9 Performance** | p95 ratio ≤ configured max; no new error classes under load |
| **G10 Target test strength** | Target mutation score ≥ source mutation score − tolerance |
| **G11 Human sign-off** | Reviewer approves the report |

Per-unit verdicts in the report: `VERIFIED`, `WEAKLY VERIFIED`, `UNVERIFIED`, `WAIVED`,
`BLOCKED`. The overall status can never be better than its worst non-waived unit.

Example report header:

```text
TypeScript/NestJS → Python/FastAPI                 Status: NOT COMPLETE
Ledger:        412/418 mapped · 4 waived · 2 MISSING (see §Missing)
Build/Types:   PASS
Unit tests:    238/245 (7 failing, 0 skipped)
Differential:  1,904/1,912 visible · 311/315 hold-out
API diff:      1 changed response schema (GET /orders/:id → `total` float vs decimal)
Authz matrix:  PASS (96 cells)
Hazards:       23/25 covered
Mutation:      source 0.78 · target 0.74
Blocked units: 2 (PaymentService, WebhookController)
```

---

## 10. Phase I: After Migration (cutover safety)

The agent **generates** these artifacts. It never deploys. Every step requires human approval.

1. **Permanent contract suite**: the harness, traces, and normalization rules are committed
   into the target repo as a CI job. Future changes that break the original behavior fail CI
   unless a trace is explicitly updated.
2. **Shadow mode kit**: config for a traffic mirror (e.g. Envoy/NGINX mirror) that sends
   production requests to the target, which writes to a **shadow database**. A comparator
   service diffs responses using the same normalization rules and emits divergence metrics.
3. **Strangler/canary routing**: per-endpoint routing config so traffic can move to the target
   endpoint by endpoint (1% → 10% → 50% → 100%).
4. **Automatic rollback criteria**: generated alert rules, for example divergence rate > X,
   5xx rate > source + Y, or p95 > Z. When one trips, traffic routes back to the source.
5. **Data safety**: if the DB schema changed, generate forward and backward migrations, a
   dual-write/backfill plan, and reconciliation queries that compare row counts and checksums
   across both stores.
6. **Runbook**: cutover steps, the rollback procedure, known waivers, and owners.
7. **Decommission checklist**: the source is kept runnable until shadow divergence has been ~0
   for N days (user-defined).

---

## 11. System Architecture

```text
Web UI / REST API ──► Queue (Redis) ──► Migration Worker
                                              │
                                     Agent Orchestrator (state machine)
          ┌───────────────┬───────────────┬───┴──────────┬────────────────┬──────────────┐
     Analyzer        Baseline/Harness   Planner     Migration Agent   Validation Agent  Reviewer Agent
          └───────────────┴───────────────┴──────┬───────┴────────────────┴──────────────┘
                                          Tool Registry (permissioned)
               ┌──────────────┬───────────────┬──┴────────────┬──────────────┐
          Repo tools     Code intelligence   Sandbox exec   Harness tools   Git tools
                         (tree-sitter + LSP)  (Docker)      (record/replay)
                                                 │
                           State: Postgres (metadata) · Git (code) · Blob store (evidence)
```

### 11.1 Code intelligence
- **tree-sitter** for uniform parsing across languages
- **Language servers** (tsserver, pyright, …) for definitions, references, and types
- Framework adapters extract CCM nodes from decorators and annotations
- Search: symbol graph + keyword search first; embeddings (pgvector) are optional, added later

### 11.2 Adapters (the only place with language/framework knowledge)

```python
class LanguageAdapter(ABC):
    name: str

    async def detect(self, repo: Repository) -> DetectionResult: ...
    async def parse(self, file: SourceFile) -> ParsedFile: ...
    async def extract_symbols(self, file: ParsedFile) -> list[Symbol]: ...
    async def find_dependencies(self, file: ParsedFile) -> list[Dependency]: ...
    def toolchain(self) -> ToolchainSpec: ...  # build/test/lint/format/typecheck commands
    def hazards(self) -> list[Hazard]: ...


class FrameworkAdapter(ABC):
    name: str

    async def detect(self, repo: Repository) -> DetectionResult: ...
    async def extract_concepts(self, repo: Repository, graph: CodeGraph) -> list[ConceptNode]: ...
    async def render_guidance(self, concepts: list[ConceptNode]) -> TargetGuidance: ...
    async def extract_surface(self, running: RunningApp) -> ApiSurface: ...  # for §5 diffs
    def hazards(self) -> list[Hazard]: ...
```

Deterministic mappings (types, common dependencies, error→status conventions) live in versioned
YAML under `mappings/`. The LLM reasons *within* them and does not replace them.

If a capability is missing (no parser, no runnable source, no adapter), the system reports
`Unsupported capability` / `Missing adapter` / `Insufficient validation`. It never guesses silently.

### 11.3 Sandbox
- Docker, one container per task, non-root, read-only base, and a workspace volume
- **Two network phases**: `install` (network allowed through a package-registry proxy) and
  `build/test/run` (no network; external services only through the record/replay proxy)
- CPU, memory, pid, and time limits; output truncation; process-group kill; container destroyed after use
- Commands come from `ToolchainSpec` allowlists. The LLM never composes shell strings.

### 11.4 Tools
`list_files, read_file, write_file, search_text, search_symbols, get_definition,
get_references, get_dependencies, run_build, run_tests, run_linter, run_formatter,
run_type_checker, run_traces, diff_surface, git_diff, git_commit, git_revert_unit`.

Permissions are declared per agent. For example, the migration agent cannot write to
`harness/`, `traces/`, or `mappings/`. `delete_file`, dependency major-version upgrades,
normalization rules, waivers, git push, and PR creation require human approval.

### 11.5 LLM layer
- `LLMProvider` interface with `generate` and `generate_structured` (Pydantic schemas). **OpenAI**
  is the first and default adapter (key and model name come from `.env`). Others plug in later.
- Prompt registry with versioned prompts per task: analysis, planning, migration, test-gen,
  diagnosis, fix, review, and hazard-detection
- Model routing per task, per-unit token budgets, response caching keyed on
  (prompt version, input hash), and prompt caching where supported
- Repository content is always passed as delimited *data*. Instructions found in it are never
  followed. Secrets are redacted before any LLM call.

### 11.6 Observability
Every agent action, tool call, and LLM call is logged with: timestamp, agent, action, target,
reason, result, tokens, latency, and cost. Runs are replayable from logs plus git.

---

## 12. Data Model (Postgres)

`projects, repositories, migration_configs, inventories, code_symbols, code_edges,
concept_nodes, ledger_entries, migration_units, unit_dependencies, unit_attempts,
traces, trace_runs, trace_diffs, normalization_rules, hazards, hazard_findings,
gate_results, evidence_artifacts, issues, waivers, approvals, agent_runs, tool_calls,
llm_calls`.

Early milestones use SQLite through the same SQLAlchemy models. Postgres is added at M9.

---

## 13. API (added at M9; the CLI comes first)

```text
POST /projects                     GET /projects/{id}
POST /projects/{id}/analyze        GET /projects/{id}/inventory
POST /projects/{id}/baseline       GET /projects/{id}/ledger
POST /projects/{id}/plan           GET /projects/{id}/plan
POST /projects/{id}/migrate        GET /projects/{id}/units
POST /projects/{id}/pause|resume|cancel
POST /projects/{id}/units/{unit}/retry|skip
GET  /projects/{id}/gates          GET /projects/{id}/issues
GET  /projects/{id}/traces/diffs   GET /projects/{id}/logs
GET  /projects/{id}/report
POST /projects/{id}/approvals/{approval_id}  (approve | reject | edit)
```

Long-running work runs in background workers, never inside a request.

---

## 14. Milestones (each has an exit test; do not start the next until it passes)

| # | Milestone | Exit criteria |
|---|---|---|
| **M1** | Repository analyzer: language, package manager, build and test tool detection; entry points; config/env discovery; tree-sitter symbols; import graph with SCCs; CLI `migrator analyze` | Snapshot tests on TS and Python fixture repos; graph and SCCs correct on a fixture with a cycle |
| **M2** | Sandbox + toolchains: install, build, and test the **source** fixtures in Docker with limits and network phases | Source fixture tests pass in sandbox; sandbox escape/limit tests pass |
| **M3** | Behavior baseline: run source app + its services (DB) in sandbox, harness, determinism controls, DB diffing, trace capture, self-consistency check, hold-out split, mutation score | Source-vs-source replay is 100% stable (with approved rules); mutation score reported |
| **M4** | CCM + NestJS/TypeORM/FastAPI/SQLAlchemy framework adapters + ledger + surface extraction + static-vs-real schema check | Ledger for fixture is complete; API/schema surface extracted on both stacks |
| **M5** | LLM layer + planner + interface-first skeleton | Skeleton for fixture compiles and boots; plan respects SCC order |
| **M6** | Unit migration loop + sealed tests + fix loop + git per unit | ≥ 80% of fixture units reach unit-test green; attempts/blocked tracked |
| **M7** | Differential validation + gates G0–G6 + report + **evaluation harness** | First full NestJS→FastAPI fixture run with a truthful report; eval runs N× and reports variance |
| **M8** | Hardening: hazards, property/fuzz, authz matrix, anti-cheat, adversarial reviewer, line coverage of source under the harness, record/replay proxy for external services, G7–G10 | Seeded bugs injected into target are caught by gates (≥ 95% of the seeded bug set) |
| **M9** | API + Redis workers + Postgres + approvals/waivers | API tests; pause/resume/cancel survive worker restart |
| **M10** | Web UI: projects, plan, progress, units, ledger, gates, trace diffs, diff viewer, logs, report | UI e2e smoke test |
| **M11** | Cutover kit (§10) + reverse direction Python/FastAPI → TS/NestJS | Contract suite runs in target CI; shadow comparator works against fixture |

**Seeded-bug testing (M8 onward)** is how the system itself is validated. Take a correct
migrated fixture, inject known semantic bugs (timezone shift, casing change, off-by-one,
dropped auth check, swallowed error), and verify the gates catch each one. A gate that
misses a seeded bug is itself a bug.

---

## 15. Evaluation Framework

For each fixture, run the migration N times (default 3) and record: gate outcomes, differential
and hold-out pass rates, ledger completeness, seeded-bug catch rate, repair iterations, blocked
units, tokens, cost, and wall time. Report the mean and spread. Keep fixtures and harness
deterministic so differences come from the agent, not the environment.

Fixtures:
- `fixtures/ts-nestjs-shop`: `auth/ users/ orders/ database/` with TypeORM, Jest, JWT auth,
  one cyclic module dependency, and deliberate hazards (decimals, dates, casing, soft-delete)
- `fixtures/py-fastapi-shop`: the equivalent app for the reverse direction

---

## 16. Repository Layout

```text
migrator/
  core/            # state machine, orchestrator, models, gates (no language knowledge)
  analysis/        # inventory, code graph, SCCs
  ccm/             # canonical concept model
  adapters/
    languages/     # typescript/, python/
    frameworks/    # nestjs/, fastapi/
  harness/         # trace capture, replay, normalization, db diff, record/replay proxy
  planning/
  migration/       # unit loop, context assembly
  validation/      # surface diffs, hazards, authz matrix, mutation, anti-cheat, perf
  llm/             # providers, prompt registry, budgets, cache
  sandbox/
  tools/
  vcs/             # local + git adapters (GitHub/GitLab later)
  cutover/         # contract suite export, shadow/canary/rollback generators
  api/  worker/  ui/
  cli.py
mappings/          # versioned YAML deterministic mappings
prompts/           # versioned prompt templates
fixtures/
evals/
tests/{unit,integration,sandbox,agent,e2e,seeded_bugs}/
docker/
```

---

## 17. Engineering Standards

Python 3.12+, full type hints, Pydantic v2, async where it helps, ruff, pyright (strict on
`core/`), pytest, structured logging (structlog), and dependency injection through
constructors. Language/framework assumptions stay out of `core/`. LLM calls go only through
`llm/`. No global mutable state. No shell strings built from user or LLM input.

---

## 18. First Task

Create the project structure and implement **M1** (Repository Analyzer + Language Detection +
Dependency Graph with SCCs), with the TS and Python fixture repos and snapshot tests. Run the
tests, confirm they pass, and stop for review before starting M2.
