# Scenarios and rules

A **scenario** is a small flow of HTTP requests, like "register a user, then create an order".
Scenarios are plain JSON and have nothing language-specific in them, so the same file runs against
the old app and the new app. Example: [fixtures/scenarios/shop.json](../fixtures/scenarios/shop.json).

## Scenario suite format

```json
{
  "description": "Shop API flows",
  "env": { "JWT_SECRET": "baseline-secret" },
  "vars": { "USER_1_TOKEN": "eyJhbGciOi..." },
  "scenarios": [
    {
      "name": "register and fetch user",
      "steps": [
        { "method": "POST", "path": "/users", "body": { "email": "a@b.com", "password": "secret123" } },
        { "method": "GET", "path": "/users/1", "headers": { "Authorization": "Bearer ${USER_1_TOKEN}" } }
      ]
    }
  ]
}
```

- `env`: extra env vars given to the app, for example a fixed JWT secret so tokens in `vars` work.
- `vars`: `${NAME}` inside any step gets replaced. An unknown name is an error, not a blank.
- Every scenario starts with **empty tables and ids starting from 1**, so `/users/1` is safe to use.
- Scenario names must be unique. About 20% of scenarios are **held out** (picked by a hash of the
  name, so always the same ones). They go to `holdout.json` and will never be shown to the agents
  that write code.

## What gets recorded for each request

- status code
- only these headers: `content-type`, `location`, `www-authenticate`
- JSON body (or text)
- database changes: rows added and removed per table (a changed row = one removed + one added)

Once per run we also record the **database schema**: columns (type, nullable, default) and
constraints (primary key, unique, foreign key). Generated constraint names are left out.

## Normalization rules

Some values change on every run, like `created_at`. `migrator baseline` plays everything twice.
If a field changes between runs, it writes a **proposed** rule to `proposed_rules.json`.
Proposed rules are **not applied**. A person must review them and pass the approved file with `--rules`.

```json
[
  { "path": "body.createdAt", "action": "timestamp", "reason": "time value changes on every run" },
  { "path": "db.users.added[*].created_at", "action": "timestamp", "reason": "..." }
]
```

- `path`: `[*]` means "every item in the list".
- `timestamp`: replaces the value with `<timestamp>`, **only if it really looks like a timestamp**.
  If the value is something else, it is left as it is, so the difference still shows.
- `ignore`: replaces the value with `<ignored>`. Please use it rarely, as every ignore rule
  means we are checking less.
