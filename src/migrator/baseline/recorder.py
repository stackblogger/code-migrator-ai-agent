"""Play scenarios against a running app and record what comes out."""

import logging
from typing import Any

import httpx

from migrator.baseline.database import Postgres, Snapshot, diff_snapshots
from migrator.baseline.environment import AppEnvironment
from migrator.baseline.models import Observation, Scenario, StepTrace, Trace
from migrator.baseline.scenarios import is_holdout

log = logging.getLogger(__name__)

# Only headers that are part of the API contract. Date, server name etc. are left out.
RECORDED_HEADERS = ("content-type", "location", "www-authenticate")
REQUEST_TIMEOUT_S = 30


def record_suite(env: AppEnvironment, scenarios: list[Scenario]) -> list[Trace]:
    with httpx.Client(base_url=env.base_url, timeout=REQUEST_TIMEOUT_S) as client:
        return [record_scenario(client, env.db, scenario) for scenario in scenarios]


def record_schema(env: AppEnvironment) -> dict:
    """Database schema after the app started (empty when the app has no database)."""
    if env.db is None:
        return {}
    schema = env.db.schema()
    log.info(
        "Recorded database schema: %d columns, %d constraints",
        len(schema["columns"]),
        len(schema["constraints"]),
    )
    return schema


def record_scenario(client: httpx.Client, db: Postgres | None, scenario: Scenario) -> Trace:
    if db:
        db.reset()
    before: Snapshot = db.snapshot() if db else {}
    steps: list[StepTrace] = []
    for number, step in enumerate(scenario.steps, start=1):
        response = client.request(step.method, step.path, headers=step.headers, json=step.body)
        after: Snapshot = db.snapshot() if db else {}
        observed = Observation(
            status=response.status_code,
            headers={h: response.headers[h] for h in RECORDED_HEADERS if h in response.headers},
            body=_body(response),
            db=diff_snapshots(before, after),
        )
        log.debug(
            "  %s step %d: %s %s -> %d (db changes: %s)",
            scenario.name,
            number,
            step.method,
            step.path,
            response.status_code,
            sorted(observed.db) or "none",
        )
        steps.append(StepTrace(request=step, observed=observed))
        before = after
    statuses = " ".join(str(s.observed.status) for s in steps)
    log.info("Scenario '%s' recorded: %s", scenario.name, statuses)
    return Trace(scenario=scenario.name, holdout=is_holdout(scenario.name), steps=steps)


def _body(response: httpx.Response) -> Any:
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text
