# Code Migrator

An AI agent which migrates a codebase from one language/framework to another
(for example TypeScript + NestJS → Python + FastAPI), and then proves the new code
behaves same as the old one.

Full design is in [PLAN.md](PLAN.md). Current status is in [docs/milestones.md](docs/milestones.md).

## Status

As of now **Milestone 1 is done**: the repository analyzer. It reads a repo and tells you:

- which languages, package managers, build/test/lint tools are used
- entry points, config files and env variables (only names, never values)
- all classes, functions, methods and their decorators
- import graph between files, cycles in it, and a safe migration order (dependencies first)
- warnings for anything it could not understand. It does not guess silently.

Supported languages as of now: **TypeScript** and **Python**. No LLM is used in this milestone.

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

## Quick start (Docker)

```bash
docker compose run --rm migrator analyze /repos/fixtures/ts-nestjs-shop
```

To analyze your own repo, set `REPOS_DIR` in `.env` (copy from `.env.example`). It gets
mounted read-only at `/repos/workspace`. Reports can be written to `/reports`, which is `./reports` on your machine.

## Running tests

```bash
uv run pytest
```

or inside Docker:

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
  cli.py           `migrator` command
fixtures/          small sample repos used in tests
tests/             unit/, integration/, snapshots/
docs/              architecture and milestone notes
```

## Configuration

Copy `.env.example` to `.env`. The OpenAI key (`OPENAI_API_KEY`) is needed only from
milestone M5 onwards, when the LLM starts writing code.
