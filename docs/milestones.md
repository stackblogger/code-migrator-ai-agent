# Milestones

Each milestone has an exit test. We go to the next one only after the exit test passes.
Details are in [PLAN.md §14](../PLAN.md).

| # | Milestone | Status |
|---|---|---|
| M1 | Repository analyzer + language detection + dependency graph | ✅ Done |
| M2 | Docker sandbox: build and test the source repo | ✅ Done |
| M3 | Behaviour baseline (run source app, record golden traces) | ✅ Done |
| M4 | Concept model + NestJS/FastAPI adapters + ledger | ✅ Done |
| M5 | OpenAI LLM layer + planner + target skeleton | ✅ Done |
| M6 | Unit migration + fix loop | ✅ Done |
| M7 | Differential validation + gates + report + evals | ⏳ Next |
| M8 | Hardening (hazards, fuzz, authz matrix, hold-out, seeded bugs) | Not started |
| M9 | API + workers + Postgres + approvals | Not started |
| M10 | Web UI | Not started |
| M11 | Cutover kit + reverse direction | Not started |

## M1: what got done

- `migrator analyze <repo>` and `migrator deps <repo> <file>` commands
- TypeScript and Python adapters using tree-sitter
- Package manager and tool detection (npm/yarn/pnpm/bun, pip/uv/poetry/pdm)
- Import graph with cycle detection and dependency-first migration order
- Two fixture repos: `ts-nestjs-shop` and `py-fastapi-shop`. Both are the same shop app
  and each has one import cycle.
- 35 tests (unit + integration + snapshot). Ruff and pyright are clean.
- Dockerfile (`app` and `dev` targets) and docker compose

**Exit test result:** both fixtures give correct snapshots, and the cycle between the two
entity/model files is detected in both languages. ✅

## M2: what got done

- `migrator verify <repo>` and `migrator cleanup` commands
- Docker sandbox with network split (install only), limits, read-only root, non-root user,
  no capabilities, command allowlist, output cap, timeout kill and container cleanup
- Workspace copy of the repo; real `.env` files are never copied
- Toolchains for TypeScript (npm/pnpm/yarn) and Python (uv / requirements.txt / poetry)
- Fixtures now have real lockfiles (`package-lock.json`, `uv.lock`), so installs are repeatable
- 71 tests. 12 of them use real Docker: 9 try to break the sandbox, 3 run full verify.

**Exit test result:** both fixtures install, build and pass their tests inside the sandbox
(jest: 3 passed, pytest: 2 passed). All 9 escape/limit tests pass. A repo with a failing test
is reported as `FAILED`. ✅

**Change from plan:** starting the source app is moved to M3, because the TS app needs Postgres,
and running app + database together belongs with trace recording.

## M3: what got done

- `migrator baseline <repo> --scenarios ... [--rules ...] [--mutants N]` command
- Logging for all main steps (`-v`, `-q`, `MIGRATOR_LOG_FORMAT=json`), also added to M1/M2 code
- Real app + Postgres run on an internal Docker network (no internet), reached only through a
  small gateway on 127.0.0.1
- Language-neutral scenario suites ([docs/scenarios.md](scenarios.md)). One shared suite,
  `fixtures/scenarios/shop.json`, with 10 scenarios runs on both apps.
- For each request: status, contract headers, body and row-level DB diff. For each run: DB schema.
- Determinism: DB reset with `RESTART IDENTITY` before each scenario, UTC, fixed locale and hash seed
- Self-consistency check (play twice, compare). Unstable fields get proposed rules, which a
  human must approve before they are used.
- About 20% hold-out scenarios, written separately to `holdout.json`
- Mutation testing that works for any language (tree-sitter operator swaps), with a repeatable pick
- 99 tests. Docker tests also check that the running app has no internet and gets no host secrets.

**Exit test result:** ✅
- Without rules, both apps are `UNSTABLE` only because of `created_at`/`createdAt`. The proposed
  rules are all `timestamp` rules and were approved into `fixtures/scenarios/*.rules.json`.
- With approved rules, both apps are `STABLE` (0 differences between runs).
- Mutation score (seed 0): **Python 92% (11/12), TypeScript 75% (6/8)**. The 3 survivors change
  nothing anyone can see (`expire_on_commit`, NestJS `whitelist`/`transform`), so every mutant
  that changes behaviour was caught.
- Mutation testing found one real gap in the first version: unique/nullable changes were not
  noticed. Recording the DB schema fixed it (Python went from 83% to 92%, TypeScript from 50% to 75%).

**Changes from plan:**
- Line coverage moved to M8. The mutation score is a stronger signal, and it works for every language.
- Record/replay proxy for external services moved to M8. The fixtures have no external calls,
  so we would be building it with nothing to test it on. For now outbound calls just fail, and
  the analyzer warns when it sees an HTTP client library.

**Already visible for later (M7):** the two apps differ, for example cancel returns 201 vs 200,
`createdAt` vs `created_at`, and invalid input gives 400 vs 422. Differential testing must catch these.

## M4: what got done

- `migrator concepts <repo> [--schema schema.json]` and `migrator ledger <source> [--target ...] [--waivers ...]`
- Canonical concept model with language-neutral keys ([docs/ledger.md](ledger.md))
- Framework adapters: NestJS (routes, guards, DTO validation, exceptions, providers),
  TypeORM (entities, columns, join columns), FastAPI (routers, `Depends` auth, Pydantic models,
  `HTTPException`), SQLAlchemy (models, columns, foreign keys)
- Schema check: columns read from code vs the real database from `baseline`
- Ledger with mapped / mismatch / missing / waived, name-style hints, target-only items, unused waivers
- 104 fast tests (+17 Docker tests)

**Exit test result:** ✅
- Surface extracted on both stacks: 5 routes, 4 request fields, 2 tables, 11 columns, 4 error codes,
  4 env vars, no notes. Static columns match the real database for both apps (0 problems).
- Ledger TypeScript → Python: 30 items, 27 mapped. The 3 others are exactly the real differences
  we already saw in M3 traces: cancel status 201 vs 200, `total` numeric string vs decimal,
  and `userId` vs `user_id` (with a hint). With the fixture waivers the ledger is complete.

## M5: what got done

- LLM layer ([docs/llm.md](llm.md)): OpenAI provider (Responses API, structured outputs), fake
  provider for tests, versioned prompts, `<repository_data>` wrapping, secret redaction, disk
  cache, usage log with tokens and time
- `migrator plan [--llm]`: units from the SCC graph in dependency order, file roles, convention
  layout; the LLM proposes layout + behaviour risks, our code validates it (one retry, then fallback)
- `migrator skeleton [--llm] [--check]`: deterministic FastAPI project from the concept model and plan
- Boot check: build + smoke test + start with Postgres + probe every route; auth routes must give
  401 without a token. The resolved `uv.lock` is saved back so later installs are frozen.
- 122 fast tests, 1 live OpenAI test (opt-in), 19 Docker tests

**Exit test result:** ✅
- Plan respects SCC order (checked in code and tests); the entity cycle is one unit.
- Skeleton for the TypeScript fixture compiles, installs, passes its smoke test and boots.
  All 4 auth routes answer 401 without a token, `POST /users` answers 422 on an empty body.
- Ledger source → skeleton: everything is mapped except the business-logic errors
  (400, 404, 409), which are M6 work. Only `HTTP 501` (the stub marker) is extra.
- Live OpenAI run: 1 call, about 4.3k tokens, answer valid on the first try.

**Found on the way:** FastAPI 0.141 wraps included routers, so walking `app.routes` no longer
lists them. The skeleton smoke test caught it; it now reads routes from `app.openapi()`.

## M6: what got done

- `migrator migrate <source> --target-dir <skeleton> [--baseline ...] [--units ...]` ([docs/migration.md](migration.md))
- Unit loop: LLM → policy check → write → stub/test check → sandbox build + mypy + full tests →
  commit, or fix with the exact error. 5 attempts (last one on the strong model), then BLOCKED
  with files restored and a report.
- Minimal context per unit; only visible traces (hold-out never read); JWT claims, never tokens
- Write permissions enforced by code; the smoke test, pyproject, lockfile and state are protected
- Git history in the generated target repo (one commit per green unit), resumable state
- Type check step (mypy) in the Python toolchain, used whenever a project declares mypy
- 131 fast tests, 5 new Docker tests for the loop with a fake LLM (green, fix, rule-breaking
  answers, blocked + restore, resume)

**Exit test result:** ✅ (goal was 80% of units green)
- Live run on the TypeScript fixture: 12 of 12 units with work are green, 0 blocked, 5 skipped
  (module wiring). About 99k tokens.

**What the live runs taught us (important):**
- Run 1 (no type check) was also 12/12 green, but replaying the M3 scenarios on the result
  gave 20 server errors. One router called `UsersService(db)`, but the service needed a second
  argument. Every unit's own tests passed because they used fakes. So "green" is not "same
  behaviour". We added mypy with `check_untyped_defs` to the loop.
- Run 2 (with type check): mypy caught problems in 6 units and the loop fixed them. Replaying
  the scenarios: 0 server errors, 22/22 status codes same as the source, database changes and
  schema the same, 16/22 responses fully the same.
- Still different (for M7 to fix through differential testing): error bodies use FastAPI's
  `{"detail": ...}` instead of NestJS's `{"message", "error", "statusCode"}` (6 requests), and
  `content-type` has no `; charset=utf-8`. M7 must also compare schemas by column name,
  not by column position.
