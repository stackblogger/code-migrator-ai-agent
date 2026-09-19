# LLM layer

All LLM calls go through `migrator/llm/`. No other code talks to a vendor SDK.

## Setup

Put these in `.env` (see `.env.example`). Empty values use the defaults.

| Setting | Default | Used for |
|---|---|---|
| `OPENAI_API_KEY` | - | required for any `--llm` command |
| `OPENAI_MODEL` | `gpt-5.6-sol` | planning, migration, fixing |
| `OPENAI_MODEL_CHEAP` | `gpt-5.6-luna` | simple, high volume tasks |
| `OPENAI_MODEL_STRONG` | `gpt-6-astra` | hard cases (blocked units, review) |

## What happens on every call

1. **Versioned prompt** from `llm/prompts/<name>.v<N>.md` (e.g. `plan_mapping.v1`).
   Repo content goes inside `<repository_data>` tags, and the system prompt says it is data,
   never instructions (prompt-injection protection).
2. **Secrets are redacted** before sending: private keys, `sk-...` keys, AWS keys, GitHub tokens,
   JWTs, passwords in database URLs, and `password = "..."` style values.
3. **Cache**: the same prompt + model + schema is answered from `.migrator-cache/llm/` for free.
4. **Structured output**: the answer must fit a Pydantic model (OpenAI Responses API
   structured outputs). No free-text parsing.
5. **Our own checks**: the answer is then validated by code. For example the planner rejects
   bad paths or missing files, retries once with the list of problems, and otherwise falls back
   to the convention layout, with a note.
6. **Usage log**: every call (task, prompt version, model, tokens, time, cached or not) is
   logged and added to `.migrator-cache/llm/usage.jsonl`.

## Tests

Tests use `FakeProvider`, so they never call the network. One live test calls OpenAI for real:

```bash
MIGRATOR_LIVE_LLM=1 uv run pytest tests/integration/test_llm_live.py
```
