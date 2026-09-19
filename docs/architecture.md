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

## Rules we follow

- **Repo content is untrusted.** Paths are checked so nothing goes outside the repo root.
  Symlinks are skipped. From `.env` files we read only key names, never values.
- **No silent failure.** If an import cannot be resolved, a package is not declared,
  or a file has syntax errors, it goes into `warnings`. We do not guess.
- **Deterministic output.** Everything is sorted, so the same repo always gives the same report.
  Snapshot tests depend on this.

## Known limits (as of M2)

- TypeScript path aliases from `tsconfig.json` (`paths`, `baseUrl`) are not resolved yet.
  Such imports show up as "not declared" warnings.
- Plain JavaScript files (`.js`) are not analyzed yet.
- The graph is at file level. Symbol level call graph will come with framework adapters (M4).
- Install steps get open internet. A package-registry-only proxy is planned for later.
- Python image is fixed at 3.12 and Node at 22. We do not read `requires-python` or `engines` yet.
- Only the root `package.json` / `pyproject.toml` is used. Monorepos are not handled yet.
- Starting the app and its database (Postgres etc.) moves to M3, where we need the app running.
