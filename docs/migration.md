# Migrating the logic (M6)

`migrator migrate` fills the skeleton with real code, one unit at a time, in plan order.

```bash
uv run migrator skeleton fixtures/ts-nestjs-shop --out out/shop-python --check
uv run migrator migrate fixtures/ts-nestjs-shop --target-dir out/shop-python --baseline baseline/ts
```

## The loop for one unit

```text
LLM writes the unit's files + tests
  → policy check (paths, protected files, syntax, no skipped tests)
  → write files → no stubs left? real tests present?
  → sandbox: build + type-check (mypy) + the WHOLE test suite
  → green: commit in the target repo
  → failed: send the exact error back to the LLM and try again
after 5 tries (the last one with the strong model): BLOCKED, files restored, report written
```

## What the LLM gets

Only what the unit needs: its source files, the current target files (skeleton stubs it must
keep), already migrated files it depends on, `app/database.py` and `app/config.py`, the plan's
risks for the unit, and the recorded behaviour for its routes from `traces.json`.

- `holdout.json` is never read. Those traces are kept for the final check (M7/M8).
- Tokens are never sent. For a JWT we only show its claims, like `{"sub": "1"}`.
- Secrets are redacted by the LLM layer, as for every call.

## Rules enforced by code (not by the prompt)

- A unit can write only its own target files and `tests/generated/test_<unit>.py`.
- Protected: `tests/test_skeleton.py`, `pyproject.toml`, `uv.lock`, `app/database.py`, `.migrator/`.
- No `pytest.skip` / `xfail`. Tests must have asserts.
- No stubs may stay in the unit's app files (HTTP 501, `MIGRATOR-STUB`, "not migrated yet").
- The whole test suite must pass, so a new unit cannot break an earlier one.
- mypy (with `check_untyped_defs`) must pass. Each unit's own tests use fakes, so they cannot
  see a wrong call into another unit. The type check can, without running anything. This was
  added after the first live run, where one router called `UsersService(db)` but the service
  needed a second argument: all unit tests passed, yet every order request gave a 500.
- Generated code runs only in the sandbox, in a workspace copy. It cannot change the target repo.

## State, git and resume

- `.migrator/state.json` in the target repo has every unit's status and every attempt
  (model, tokens, where it failed, short error). It is saved after every attempt.
- The target repo gets its own git history on branch `migration`, one commit per green unit,
  authored as `code-migrator`. Your source repo is never touched.
- Run `migrate` again to continue: green and skipped units are skipped. `--units u09,u10` runs
  only some units. A blocked unit is tried again from scratch on the next run.
- Blocked units have a report in `.migrator/blocked/<unit>.md` with every attempt and the last error.
