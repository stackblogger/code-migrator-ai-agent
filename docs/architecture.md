# Architecture

Short notes on how the code is built. Full design is in [PLAN.md](../PLAN.md).

## Main idea

The core never knows any language. All language knowledge sits inside **adapters**.
To support a new language, you write one adapter and add it in
`adapters/languages/__init__.py`. No other change is needed.

## Flow of `migrator analyze`

```text
LocalRepository  →  list files (skips node_modules, .git, venv, symlinks)
      ↓
for each LanguageAdapter:
   parse files (tree-sitter)  →  symbols, imports, env vars
   resolve imports            →  file inside repo, or external package
   read manifests             →  package.json / pyproject.toml / requirements.txt
   detect tools, entry points
      ↓
CodeGraph (networkx)  →  edges, cycles (SCCs), migration order
      ↓
RepoReport (Pydantic)  →  JSON file + short terminal summary
```

## Flow of `migrator verify`

```text
analyze repo  →  adapter.toolchain()  →  image + fixed steps (install, build, test)
      ↓
Workspace: temp copy of the repo (no .env files, no node_modules)
      ↓
for each step: fresh container → run → collect exit code, time, output tail → remove container
      ↓
stop at first failure  →  SandboxRun: PASSED / FAILED / INCOMPLETE
```

## Sandbox rules

| Rule | How |
|---|---|
| No network while building or testing | `--network none`; only `install` steps get network |
| Limits | memory (no swap), CPUs, process count, timeout (container killed), output cap (last 200 KB kept) |
| Cannot change the image or see the host | `--read-only` root, only `/workspace` and a small `/tmp` are writable |
| No extra powers | non-root user, `--cap-drop ALL`, `no-new-privileges`, `--init` to reap processes |
| No secrets | host env vars are not passed in; real `.env` files are not copied |
| No shell | commands are argument lists from adapters, and `argv[0]` must be in an allowlist |
| Honest result | no tests = `INCOMPLETE`, memory kill and timeout are reported separately |

Images used: `node:22-bookworm-slim` and `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`.

## Flow of `migrator baseline`

```text
analyze  →  adapter.launch_info()  →  RunSpec (command, port, env, services)
   ↓                                    (.migrator.toml can override)
Workspace copy → install + build in sandbox (same as verify, without tests)
   ↓
AppEnvironment:
   host 127.0.0.1:random ──► gateway (socat) ──► app ──► postgres
                              └──── internal network, no internet ────┘
   ↓
for run in 1..N:  record DB schema; for each scenario: reset DB → send requests → record status/body/DB diff
   ↓
normalize with approved rules → compare runs → STABLE / UNSTABLE (+ proposed rules)
   ↓
optional mutation testing → baseline.json, traces.json, holdout.json, schema.json, app.log
```

**Determinism controls:** DB tables truncated with `RESTART IDENTITY` before every scenario,
`TZ=UTC`, fixed locale, `PYTHONHASHSEED=0`, only contract headers recorded (no `Date`),
fixed secrets and tokens through the scenario suite. Anything still unstable is caught by the
second run and needs a human-approved rule.

**Running app isolation:** app and DB are on an `--internal` Docker network (no internet).
The app container has the same lock-down as sandbox steps. Postgres keeps data in memory
(tmpfs) and has no port on the host; we read it with `docker exec psql`. The gateway is the
only way in and listens only on 127.0.0.1.

**Mutation testing:** tree-sitter finds operator tokens (`<=`, `===`, `&&`, `+`, `true`, ...) in
source files. Each picked mutant is applied, the app is rebuilt, started and replayed.
Killed = some trace changed (good). Survived = weak spot in scenarios. Did not build = not counted.
Same seed picks the same mutants every time.

## Flow of `migrator concepts` and `migrator ledger`

```text
analyze → for each language: framework adapters whose packages are in the manifest
        → tree-sitter → concept nodes (route, input_field, table, column, error, env_var)
        → ConceptModel  (+ optional check of columns against the real DB schema)

ledger: group source and target nodes by (kind, key) → mapped / mismatch / missing
        → apply waivers → list target-only items → complete or not
```

Framework adapters live in `adapters/frameworks/` and follow `base.py`: `packages` (for
detection) and `extract(files)` which returns nodes and notes. Adding a framework means one
new file and one line in `adapters/frameworks/__init__.py`.

## Flow of `migrator plan` and `migrator skeleton`

```text
analyze + concepts → units = SCC groups in dependency order (from M1 graph)
                   → role per file (api, model, schema, guard, service, wiring, config, entrypoint, test)
                   → target file by convention layout (planning/layout.py)
                   → [--llm] OpenAI proposes idiomatic layout + risks → validated → or fallback
                   → MigrationPlan (order is checked: every unit after its dependencies)

skeleton: concepts + plan → FastAPI renderer (skeleton/fastapi/):
          models (exact column names/types/defaults), Pydantic schemas (same validation),
          routes (same method/path/status, auth dependency fails closed, handlers answer 501),
          config, main.py, pyproject (deps from mappings/*.toml), smoke test
          → [--check] sandbox install/build/test → boot with Postgres → probe every route
```

The skeleton is made by code, not by the LLM, because it is pure structure and must be exact.
The LLM only chooses the layout (and lists risks). Logic comes in M6.

## Flow of `migrator migrate`

See [migration.md](migration.md). In short: for each unit in plan order, build a minimal
context → LLM (structured `UnitChange`) → policy check → write → stub/test check → sandbox build
+ mypy + full test suite → commit, or send the error back. Max 5 attempts, then BLOCKED + restore.

## Logging

Every module uses `logging.getLogger(__name__)`; setup is in `log.py`. Logs go to stderr.
Main steps log at INFO (analysis, each sandbox step, containers started/removed, each scenario,
each mutant). Docker commands, per-file parsing and per-request details are at DEBUG (`-v`).
Failures log at ERROR with the reason (exit code, timeout, memory limit, app logs tail).

## Language adapter contract

See `adapters/languages/base.py`. Every adapter gives:

| Method | What it does |
|---|---|
| `owns(path)` / `is_test_file(path)` | Which files belong to this language |
| `parse_file(path, source)` | Symbols, imports, env vars from one file |
| `resolve_imports(imports, files)` | Map each import to a repo file or an external package |
| `read_manifests(repo)` | Dependencies and package manager |
| `detect_tools(repo, manifests)` | build / test / lint / format / typecheck tools |
| `find_entry_points(...)` | Where the app starts |
| `is_builtin(pkg)` / `is_declared(pkg, manifests)` | Used to warn about missing dependencies |
| `toolchain(repo, inventory)` | Docker image and fixed install/build/test commands |
| `launch_info(repo, inventory)` | Start command, services (Postgres), database URL format |
| `syntax_tree(path, source)` | Raw tree-sitter tree, used by mutation testing |

## Rules we follow

- **Repo content is untrusted.** Paths are checked so nothing goes outside the repo root.
  Symlinks are skipped. From `.env` files we read only key names, never values.
- **No silent failure.** If an import cannot be resolved, a package is not declared,
  or a file has syntax errors, it goes into `warnings`. We do not guess.
- **Deterministic output.** Everything is sorted, so the same repo always gives the same report.
  Snapshot tests depend on this.

## Known limits (as of M3)

- TypeScript path aliases from `tsconfig.json` (`paths`, `baseUrl`) are not resolved yet.
  Such imports show up as "not declared" warnings.
- Plain JavaScript files (`.js`) are not analyzed yet.
- The graph is at file level. Symbol level call graph will come with framework adapters (M4).
- Install steps get open internet. A package-registry-only proxy is planned for later.
- Python image is fixed at 3.12 and Node at 22. We do not read `requires-python` or `engines` yet.
- Only the root `package.json` / `pyproject.toml` is used. Monorepos are not handled yet.
- Only HTTP apps and only Postgres as a service. Other databases and queues come later.
- No record/replay of external HTTP services yet. Outbound calls simply fail (no internet),
  and the analyzer warns when it sees an HTTP client library.
- Scenarios are written by hand for now. Generating them from routes comes with M4/M5.
- Line coverage is not measured yet (planned for M8). The mutation score is the strength signal for now.
- Framework adapters cover the common patterns only. For example FastAPI `include_router(prefix=...)`,
  NestJS dynamic modules, TypeORM naming strategies and SQLAlchemy imperative mapping are not read yet.
  Unsupported patterns are reported as notes. The schema check against the real database catches
  column mistakes.
- Only one target is supported for now: `python-fastapi`. Relationships between models and
  response models are not generated yet (M6). Enum defaults like `OrderStatus.Pending` are
  reported as notes and must be set by hand or in M6.
- The ledger compares static facts only. Whether mapped items really behave the same is checked
  by differential testing in M7.
