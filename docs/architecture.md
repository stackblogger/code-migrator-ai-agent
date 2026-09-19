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

## Rules we follow

- **Repo content is untrusted.** Paths are checked so nothing goes outside the repo root.
  Symlinks are skipped. From `.env` files we read only key names, never values.
- **No silent failure.** If an import cannot be resolved, a package is not declared,
  or a file has syntax errors, it goes into `warnings`. We do not guess.
- **Deterministic output.** Everything is sorted, so the same repo always gives the same report.
  Snapshot tests depend on this.

## Known limits (as of M1)

- TypeScript path aliases from `tsconfig.json` (`paths`, `baseUrl`) are not resolved yet.
  Such imports show up as "not declared" warnings.
- Plain JavaScript files (`.js`) are not analyzed yet.
- The graph is at file level. Symbol level call graph will come with framework adapters (M4).
