"""Build the minimal context for one unit: its source, its current target files, the
already migrated files it depends on, recorded behaviour for its routes, and its risks."""

import base64
import json
import re
import tomllib
from pathlib import Path

from migrator.baseline.models import Trace
from migrator.llm import as_data
from migrator.migration.policy import allowed_paths
from migrator.planning.models import MigrationPlan, MigrationUnit
from migrator.repository import LocalRepository

MAX_FILE_CHARS = 20_000
MAX_TRACE_CHARS = 15_000
SHARED_FILES = ["app/database.py", "app/config.py"]


def load_visible_traces(baseline_dir: Path | None) -> list[Trace]:
    """Only `traces.json`. The hold-out file is never read here, on purpose."""
    if baseline_dir is None:
        return []
    raw = json.loads((baseline_dir / "traces.json").read_text())
    return [t for t in (Trace.model_validate(item) for item in raw) if not t.holdout]


def unit_context(
    unit: MigrationUnit,
    plan: MigrationPlan,
    source: LocalRepository,
    target: Path,
    traces: list[Trace],
) -> dict[str, str]:
    units = {u.id: u for u in plan.units}
    dependency_files = sorted(
        {f.target for d in unit.depends_on for f in units[d].files if f.target} | set(SHARED_FILES)
    )
    dependency_files = [p for p in dependency_files if p not in allowed_paths(unit)]
    return {
        "source_stack": f"{plan.source_language} ({', '.join(plan.source_frameworks)})",
        "target_stack": "Python 3.12 + FastAPI + SQLAlchemy 2 + Pydantic 2",
        "unit_id": unit.id,
        "allowed": "\n".join(f"- {p}" for p in allowed_paths(unit)),
        "risks": "\n".join(f"- {r}" for r in unit.risks) or "- none listed",
        "concepts": "\n".join(f"- {c}" for c in unit.concepts) or "- none",
        "dependencies": ", ".join(_project_dependencies(target)),
        "source_files": as_data(
            _files_text(
                [
                    (
                        f"{f.source} (role: {f.role.value}, becomes: {f.target})",
                        _read(source.root / f.source),
                    )
                    for f in unit.files
                ]
            )
        ),
        "target_files": as_data(
            _files_text([(p, _read(target / p) or "(new file)") for p in allowed_paths(unit)])
        ),
        "dependency_files": as_data(
            _files_text([(p, _read(target / p)) for p in dependency_files if (target / p).exists()])
            or "(none)"
        ),
        "traces": as_data(_traces_text(unit, traces)),
    }


def _files_text(files: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"### {name}\n```\n{content}\n```" for name, content in files)


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    text = path.read_text()
    if len(text) > MAX_FILE_CHARS:
        return text[:MAX_FILE_CHARS] + f"\n... (cut, file has {len(text)} characters)"
    return text


def _project_dependencies(target: Path) -> list[str]:
    data = tomllib.loads((target / "pyproject.toml").read_text())
    return data.get("project", {}).get("dependencies", [])


def _traces_text(unit: MigrationUnit, traces: list[Trace]) -> str:
    """Whole scenarios that call one of this unit's routes, as compact JSON lines."""
    patterns = [
        _route_pattern(c.removeprefix("route:")) for c in unit.concepts if c.startswith("route:")
    ]
    if not patterns or not traces:
        return "(no recorded traces for this unit)"
    lines: list[str] = []
    for trace in traces:
        if not any(
            p.match(f"{s.request.method} {s.request.path}") for s in trace.steps for p in patterns
        ):
            continue
        lines.append(f"Scenario '{trace.scenario}' (starts with an empty database):")
        for number, step in enumerate(trace.steps, start=1):
            request = {
                "method": step.request.method,
                "path": step.request.path,
                "body": step.request.body,
            }
            if "Authorization" in step.request.headers:
                request["token"] = _token_claims(step.request.headers["Authorization"])
            observed = {"status": step.observed.status, "body": step.observed.body}
            lines.append(f"  {number}. {json.dumps(request)} -> {json.dumps(observed)}")
    text = "\n".join(lines) or "(no recorded traces for this unit)"
    return text if len(text) <= MAX_TRACE_CHARS else text[:MAX_TRACE_CHARS] + "\n... (cut)"


def _token_claims(header: str) -> dict | str:
    """Claims of a JWT (not secret). The token itself is never put in a prompt."""
    token = header.removeprefix("Bearer ").strip()
    parts = token.split(".")
    if len(parts) != 3:
        return "a token that is not a valid JWT"
    try:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        return {"valid_jwt_with_claims": json.loads(base64.urlsafe_b64decode(padded))}
    except ValueError:
        return "a token that is not a valid JWT"


def _route_pattern(route_key: str) -> re.Pattern[str]:
    """ "POST /orders/{}/cancel" -> matches "POST /orders/1/cancel"."""
    escaped = re.escape(route_key).replace(re.escape("{}"), "[^/]+")
    return re.compile(f"^{escaped}$")
