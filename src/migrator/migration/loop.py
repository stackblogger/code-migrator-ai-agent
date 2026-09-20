"""Migrate the plan unit by unit: migrate -> check -> fix, then commit or block.

For every unit (in plan order):
1. Ask the LLM for the unit's target files and tests (minimal context, see context.py).
2. Check paths and syntax (policy.py). Nothing outside the unit's own files can be written.
3. Write the files, then check no stubs are left and real tests exist.
4. Build and run the whole test suite in the sandbox (checker.py).
5. Green -> commit in the target repo. Failed -> send the error back and try again.
6. After `max_attempts` the unit is BLOCKED: its files are restored and a report is written.
State is saved after every attempt, so a stopped run can be resumed.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from migrator.baseline.models import Trace
from migrator.llm import LLMClient, LLMError, as_data, load_prompt
from migrator.migration.checker import SandboxChecker
from migrator.migration.context import load_visible_traces, unit_context
from migrator.migration.gitrepo import GitRepo
from migrator.migration.models import Attempt, MigrationState, UnitChange, UnitState, UnitStatus
from migrator.migration.policy import allowed_paths, check_change, check_done, target_files
from migrator.planning.models import MigrationPlan, MigrationUnit
from migrator.repository import LocalRepository
from migrator.sandbox import DockerSandbox

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
PLAN_FILE = ".migrator/plan.json"


@dataclass
class Session:
    source: LocalRepository
    target: Path
    plan: MigrationPlan
    llm: LLMClient
    checker: SandboxChecker
    git: GitRepo
    state: MigrationState
    traces: list[Trace]
    max_attempts: int


def run_migration(
    source: LocalRepository,
    target: Path,
    llm: LLMClient,
    baseline_dir: Path | None = None,
    only_units: set[str] | None = None,
    max_attempts: int = MAX_ATTEMPTS,
    sandbox: DockerSandbox | None = None,
) -> tuple[MigrationPlan, MigrationState]:
    plan = MigrationPlan.model_validate_json((target / PLAN_FILE).read_text())
    git = GitRepo(target)
    git.ensure()
    state = MigrationState.load(target)
    traces = load_visible_traces(baseline_dir)
    log.info(
        "Migrating %d units of %s (%d visible traces)",
        len(plan.units),
        plan.source_repo,
        len(traces),
    )

    with SandboxChecker(LocalRepository(target), sandbox) as checker:
        session = Session(source, target, plan, llm, checker, git, state, traces, max_attempts)
        for unit in plan.units:
            if only_units and unit.id not in only_units:
                continue
            unit_state = state.units.setdefault(unit.id, UnitState(id=unit.id))
            if unit_state.status in (UnitStatus.GREEN, UnitStatus.SKIPPED):
                log.info("%s already %s, skipping", unit.id, unit_state.status.value)
                continue
            if not target_files(unit):
                unit_state.status = UnitStatus.SKIPPED
                unit_state.notes.append("no target file (e.g. module wiring), nothing to migrate")
                log.info("%s skipped: no target file", unit.id)
                state.save(target)
                continue
            _migrate_unit(session, unit, unit_state)
    git.commit("Record migration state")
    return plan, state


def _migrate_unit(session: Session, unit: MigrationUnit, unit_state: UnitState) -> None:
    started = time.monotonic()
    sources = ", ".join(f.source for f in unit.files)
    log.info("=== %s: %s -> %s", unit.id, sources, ", ".join(target_files(unit)))
    unit_state.attempts = []
    context = unit_context(unit, session.plan, session.source, session.target, session.traces)
    last_files: dict[str, str] = {}
    problem_stage, problem_text = "", ""

    for number in range(1, session.max_attempts + 1):
        kind = "migrate" if number == 1 else "fix"
        tier = "strong" if number == session.max_attempts and number > 1 else "default"
        values = dict(context)
        if kind == "fix":
            values |= {
                "attempt": str(number - 1),
                "stage": problem_stage,
                "error": as_data(problem_text),
                "attempt_files": as_data(_files_text(last_files) or "(no files were written)"),
            }
        attempt = Attempt(
            number=number, kind=kind, model=session.llm.settings.model_for(tier), passed=False
        )
        unit_state.attempts.append(attempt)

        try:
            change = session.llm.structured(
                f"{kind}_unit", load_prompt(f"{kind}_unit"), values, UnitChange, tier
            )
        except LLMError as error:
            _fail(attempt, "llm", str(error))
            problem_stage, problem_text = "llm", str(error)
            session.state.save(session.target)
            continue
        finally:
            _count_tokens(attempt, session.llm)

        unit_state.notes = change.notes
        last_files = {f.path: f.content for f in change.files}
        stage, text = _try_change(session, unit, unit_state, last_files)
        if stage is None:
            attempt.passed = True
            unit_state.status = UnitStatus.GREEN
            session.state.save(session.target)
            unit_state.commit = session.git.commit(
                f"{unit.id}: migrate {sources} (attempt {number})"
            )
            session.state.save(session.target)  # the commit id is saved with the next commit
            log.info(
                "%s GREEN after %d attempt(s) in %.0fs", unit.id, number, time.monotonic() - started
            )
            return
        _fail(attempt, stage, text)
        problem_stage, problem_text = stage, text
        session.state.save(session.target)

    _block(session, unit, unit_state, problem_stage, problem_text)
    log.error(
        "%s BLOCKED after %d attempts (last failure: %s)",
        unit.id,
        session.max_attempts,
        problem_stage,
    )


def _try_change(
    session: Session, unit: MigrationUnit, unit_state: UnitState, files: dict[str, str]
) -> tuple[str | None, str]:
    """Returns (None, "") when green, else (failed stage, error text)."""
    problems = check_change(unit, files)
    if problems:
        return "policy", "\n".join(problems)

    _restore_unit(session, unit)  # start each attempt from the committed state
    for path, content in files.items():
        destination = session.target / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)
    unit_state.files_written = sorted(files)

    current = {
        p: (session.target / p).read_text()
        for p in allowed_paths(unit)
        if (session.target / p).exists()
    }
    problems = check_done(unit, current)
    if problems:
        return "not_done", "\n".join(problems)

    result = session.checker.check()
    if not result.ok:
        return result.stage or "build", result.output
    return None, ""


def _block(
    session: Session, unit: MigrationUnit, unit_state: UnitState, stage: str, text: str
) -> None:
    _restore_unit(session, unit)
    unit_state.status = UnitStatus.BLOCKED
    report = session.target / ".migrator" / "blocked" / f"{unit.id}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {unit.id} is blocked",
        "",
        f"Source: {', '.join(f.source for f in unit.files)}",
        f"Target: {', '.join(target_files(unit))}",
        "",
        "## Attempts",
        "",
        *[f"- {a.number} ({a.kind}, {a.model}): failed at {a.stage}" for a in unit_state.attempts],
        "",
        f"## Last failure ({stage})",
        "",
        "```",
        text[-4000:],
        "```",
        "",
        "Files were restored to the last commit. Fix by hand, or retry with more attempts.",
    ]
    report.write_text("\n".join(lines) + "\n")
    session.state.save(session.target)
    session.git.commit(f"{unit.id}: blocked, see .migrator/blocked/{unit.id}.md")


def _restore_unit(session: Session, unit: MigrationUnit) -> None:
    session.git.restore(allowed_paths(unit))


def _fail(attempt: Attempt, stage: str, text: str) -> None:
    attempt.stage = stage
    attempt.error = text.strip().splitlines()[-1][:300] if text.strip() else stage
    log.warning("Attempt %d failed at %s: %s", attempt.number, stage, attempt.error)


def _count_tokens(attempt: Attempt, llm: LLMClient) -> None:
    if llm.calls:
        attempt.input_tokens = llm.calls[-1].usage.input_tokens
        attempt.output_tokens = llm.calls[-1].usage.output_tokens


def _files_text(files: dict[str, str]) -> str:
    return "\n\n".join(f"### {path}\n```\n{content}\n```" for path, content in files.items())
