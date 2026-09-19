# Milestones

Each milestone has an exit test. We go to the next one only after the exit test passes.
Details are in [PLAN.md §14](../PLAN.md).

| # | Milestone | Status |
|---|---|---|
| M1 | Repository analyzer + language detection + dependency graph | ✅ Done |
| M2 | Docker sandbox: build and test the source repo | ⏳ Next |
| M3 | Behaviour baseline (record golden traces from source) | Not started |
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
