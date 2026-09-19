# Milestones

Each milestone has an exit test. We go to the next one only after the exit test passes.
Details are in [PLAN.md §14](../PLAN.md).

| # | Milestone | Status |
|---|---|---|
| M1 | Repository analyzer + language detection + dependency graph | ✅ Done |
| M2 | Docker sandbox: build and test the source repo | ✅ Done |
| M3 | Behaviour baseline (run source app, record golden traces) | ✅ Done |
| M4 | Concept model + NestJS/FastAPI adapters + ledger | ⏳ Next |
| M5 | OpenAI LLM layer + planner + target skeleton | Not started |
| M6 | Unit migration + fix loop | Not started |
| M7 | Differential validation + gates + report + evals | Not started |
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
