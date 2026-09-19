# Milestones

Each milestone has an exit test. We go to the next one only after the exit test passes.
Details are in [PLAN.md §14](../PLAN.md).

| # | Milestone | Status |
|---|---|---|
| M1 | Repository analyzer + language detection + dependency graph | ✅ Done |
| M2 | Docker sandbox: build and test the source repo | ✅ Done |
| M3 | Behaviour baseline (run source app, record golden traces) | ⏳ Next |
| M4 | Concept model + NestJS/FastAPI adapters + ledger | Not started |
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
