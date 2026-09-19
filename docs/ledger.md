# Concepts and ledger

## Concepts

Framework adapters read the code with tree-sitter and write down **concepts** in a
language-neutral way. Each concept has a **key**, and the same thing gets the same key in
every language, so the old app and the new app can be matched.

| Kind | Key example | Compared attributes |
|---|---|---|
| route | `POST /orders/{}/cancel` (param names do not matter) | status, auth |
| input_field | `POST /users body.email` | constraints, required |
| table | `orders` | - |
| column | `orders.user_id` | nullable, unique, primary_key, references |
| error | `HTTP 404` (raised on purpose in code) | - |
| env_var | `DATABASE_URL` | - |

Validation rules use the same words in every language. For example `@IsEmail()` in NestJS and
`EmailStr` in Pydantic both become `email, string`. `@MinLength(8)` and `Field(min_length=8)`
both become `min_length=8`.

Adapters never guess silently. Anything they see but do not understand is written to `notes`
(for example `HttpException` with a status that is not a plain number).

**Checking the adapters against reality:** `migrator concepts <repo> --schema schema.json`
compares the columns read from ORM code with the real database schema recorded by `baseline`.
Any difference is reported. For both fixtures the result is "no problems".

## Ledger

`migrator ledger <source> --target <target>` puts every source item in one of these states:

| Status | Meaning |
|---|---|
| mapped | found in target, same attributes (behaviour is verified later, in M7) |
| mismatch | found in target, but an attribute differs, e.g. `status: 201 vs 200` |
| missing | not found in target. A hint is shown when a similar name exists (`userId` vs `user_id`) |
| waived | missing or mismatch, but a person accepted it with a reason |

Items that exist only in the target are listed too, so nothing extra slips in silently.
Without `--target`, every item is `missing`. That is the full list of things the migration must deliver.

The ledger is **complete** only when every row is `mapped` or `waived`.

## Waivers

```json
[
  { "key": "orders.userId", "reason": "renamed to user_id, clients updated", "approved_by": "Asha" }
]
```

A waiver only applies to a `missing` or `mismatch` row. A waiver that matches nothing is
reported, so old waivers do not pile up. The file in `fixtures/ledger/` is test data, not a
real approval: the two sample apps differ on purpose so later milestones have real differences to catch.
