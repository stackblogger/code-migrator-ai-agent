# Code Migrator

An AI agent which migrates a codebase from one language/framework to another
(for example TypeScript + NestJS → Python + FastAPI), and then proves the new code
behaves same as the old one.

Full design is in [PLAN.md](PLAN.md). Current status is in [docs/milestones.md](docs/milestones.md).

## Status

**Milestones 1 and 2 are done.**

**M1: repository analyzer.** It reads a repo and tells you:

- which languages, package managers, build/test/lint tools are used
- entry points, config files and env variables (only names, never values)
- all classes, functions, methods and their decorators
- import graph between files, cycles in it, and a safe migration order (dependencies first)
- warnings for anything it could not understand. It does not guess silently.

**M2: Docker sandbox.** `migrator verify` copies the repo, then installs, builds and runs its
tests inside locked-down containers. No network (except for install), memory/CPU/process/time
limits, read-only root, non-root user. Real `.env` files are never copied in.

Supported languages as of now: **TypeScript** and **Python**. No LLM is used yet.

## Quick start (local)

Needs Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

```bash
uv run migrator analyze fixtures/ts-nestjs-shop
```

Save the full JSON report:

```bash
uv run migrator analyze fixtures/ts-nestjs-shop --out report.json
```

See what a file depends on (add `--reverse` to see who uses it, `--transitive` for indirect ones):

```bash
uv run migrator deps fixtures/py-fastapi-shop app/orders/service.py
```

Install, build and test a repo inside the sandbox (needs Docker running):

```bash
uv run migrator verify fixtures/ts-nestjs-shop
```

Exit code is 0 only when every step passes **and** tests were actually run. If a repo has
no tests, the result is `INCOMPLETE`, not `PASSED`. Add `--out results.json` for full logs.
If a run crashes midway, `uv run migrator cleanup` removes leftover containers.

## Quick start (Docker)

```bash
docker compose run --rm migrator analyze /repos/fixtures/ts-nestjs-shop
```

To analyze your own repo, set `REPOS_DIR` in `.env` (copy from `.env.example`). It gets
mounted read-only at `/repos/workspace`. Reports can be written to `/reports`, which is `./reports` on your machine.

Please note: run `migrator verify` from your machine, not from this container. Giving the
container access to Docker would give it full control of your machine, which defeats the sandbox.

## Running tests

```bash
uv run pytest
```

Tests marked `docker` start real containers and take 2-3 minutes. Skip them with
`uv run pytest -m "not docker"`. They are skipped on their own when Docker is not running.

Or inside Docker (docker tests get skipped there):

```bash
docker compose run --rm tests
```

If you change the analyzer output on purpose, refresh the snapshots with
`UPDATE_SNAPSHOTS=1 uv run pytest` and check the diff before committing.

## Project layout

```text
src/migrator/
  core/            shared data models
  repository/      safe read-only access to a repo
  adapters/
    languages/     one package per language (typescript/, python/)
  analysis/        analyzer, dependency graph, config/env inventory, summary
  sandbox/         Docker sandbox, workspace copy, step runner, verify
  cli.py           `migrator` command
fixtures/          small sample repos used in tests
tests/             unit/, integration/, sandbox/, snapshots/
docs/              architecture and milestone notes
```

## Configuration

Copy `.env.example` to `.env`. The OpenAI key (`OPENAI_API_KEY`) is needed only from
milestone M5 onwards, when the LLM starts writing code.
