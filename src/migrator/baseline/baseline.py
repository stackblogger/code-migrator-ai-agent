"""Create a behaviour baseline: build the source app, run scenarios twice, check stability.

Steps:
1. Analyze the repo, pick the language that knows how to start the app.
2. Install and build in the sandbox (M2).
3. Start app + database in an isolated network.
4. Play every scenario `runs` times (fresh database for each scenario).
5. Compare the runs. Any field that changes between runs is unstable; we propose a rule
   for it, but only rules approved by a human are applied.
6. Optionally, run mutation testing to measure how strong the traces are.
"""

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from migrator.adapters.languages import LanguageAdapter, default_adapters
from migrator.analysis import analyze
from migrator.baseline.compare import compare_schemas, compare_traces, normalize_trace
from migrator.baseline.environment import AppEnvironment
from migrator.baseline.models import (
    BaselineReport,
    BaselineStatus,
    Difference,
    MutationReport,
    Trace,
)
from migrator.baseline.mutation import (
    MutationContext,
    find_mutants,
    pick_mutants,
    run_mutation_testing,
)
from migrator.baseline.normalize import propose_rules
from migrator.baseline.recorder import record_schema, record_suite
from migrator.baseline.runspec import build_run_spec
from migrator.baseline.scenarios import load_rules, load_suite
from migrator.core.models import LanguageInventory, LaunchInfo, RepoReport
from migrator.repository import LocalRepository
from migrator.sandbox import DockerSandbox, RunStatus
from migrator.sandbox.runner import run_toolchain
from migrator.sandbox.workspace import Workspace

log = logging.getLogger(__name__)

FAILED_OUTPUT_LINES = 20


@dataclass
class BaselineResult:
    report: BaselineReport
    traces: list[Trace]  # normalized traces from the first run
    schema: dict  # database schema (columns and constraints)
    app_logs: str = ""


def create_baseline(
    repo: LocalRepository,
    suite_path: Path,
    rules_path: Path | None = None,
    runs: int = 2,
    mutants: int = 0,
    sandbox: DockerSandbox | None = None,
) -> BaselineResult:
    started = time.monotonic()
    sandbox = sandbox or DockerSandbox()
    suite = load_suite(suite_path)
    rules = load_rules(rules_path)
    base = {
        "repo": repo.name,
        "runs": runs,
        "scenarios": len(suite.scenarios),
        "holdout_scenarios": 0,
        "rules_applied": rules,
    }

    picked = _pick_language(repo, analyze(repo))
    if picked is None:
        return _failed(base, "", ["No supported language found in this repo"])
    adapter, inventory, launch, env_names = picked
    toolchain = adapter.toolchain(repo, inventory)
    spec = build_run_spec(repo, toolchain, launch, env_names, suite.env)
    base["language"] = inventory.language
    notes = list(spec.notes)

    with Workspace(repo) as workspace:
        build = run_toolchain(toolchain, workspace.path, sandbox, only={"install", "build"})
        if build.status != RunStatus.PASSED:
            failed_step = build.steps[-1] if build.steps else None
            tail = failed_step.output.splitlines()[-FAILED_OUTPUT_LINES:] if failed_step else []
            return _failed(base, inventory.language, notes + build.notes + tail)

        try:
            with AppEnvironment(spec, workspace.path, sandbox) as env:
                all_runs, schemas = [], []
                for number in range(1, runs + 1):
                    log.info("Recording run %d of %d", number, runs)
                    schemas.append(record_schema(env))
                    traces = record_suite(env, suite.scenarios)
                    all_runs.append([normalize_trace(t, rules) for t in traces])
            app_logs = env.final_app_logs
        except (RuntimeError, httpx.HTTPError) as error:
            log.error("App failed: %s", error)
            return _failed(base, inventory.language, [*notes, f"App failed: {error}"])

        differences: list[Difference] = []
        for other_run, other_schema in zip(all_runs[1:], schemas[1:], strict=True):
            differences += compare_schemas(schemas[0], other_schema)
            differences += compare_traces(all_runs[0], other_run)
        status = BaselineStatus.UNSTABLE if differences else BaselineStatus.STABLE
        log.info("Self-consistency check: %s (%d differences)", status.value, len(differences))

        mutation: MutationReport | None = None
        if mutants and status == BaselineStatus.STABLE:
            ctx = MutationContext(
                workspace.path,
                toolchain,
                spec,
                sandbox,
                suite.scenarios,
                all_runs[0],
                schemas[0],
                rules,
            )
            candidates = find_mutants(workspace.path, adapter, inventory.source_files)
            mutation = run_mutation_testing(pick_mutants(candidates, mutants), ctx)
        elif mutants:
            notes.append("Mutation testing skipped, because the baseline is not stable")

    traces = all_runs[0]
    report = BaselineReport(
        **{**base, "holdout_scenarios": sum(t.holdout for t in traces)},
        status=status,
        differences=differences,
        proposed_rules=propose_rules([(d.path, d.first, d.second) for d in differences]),
        mutation=mutation,
        notes=notes,
    )
    log.info("Baseline finished in %.1fs: %s", time.monotonic() - started, status.value.upper())
    return BaselineResult(report=report, traces=traces, schema=schemas[0], app_logs=app_logs)


def write_baseline(result: BaselineResult, out_dir: Path) -> None:
    """baseline.json (report), traces.json, holdout.json (sealed), schema.json, app.log."""
    out_dir.mkdir(parents=True, exist_ok=True)
    visible = [t for t in result.traces if not t.holdout]
    holdout = [t for t in result.traces if t.holdout]
    files = {
        "baseline.json": result.report.model_dump_json(indent=2),
        "traces.json": _json_list(visible),
        "holdout.json": _json_list(holdout),
        "schema.json": json.dumps(result.schema, indent=2),
        "app.log": result.app_logs,
    }
    if result.report.proposed_rules:
        files["proposed_rules.json"] = _json_list(result.report.proposed_rules)
    for name, content in files.items():
        (out_dir / name).write_text(content + "\n")
    log.info("Baseline written to %s (%s)", out_dir, ", ".join(files))


def _pick_language(
    repo: LocalRepository, analysis: RepoReport
) -> tuple[LanguageAdapter, LanguageInventory, LaunchInfo, set[str]] | None:
    adapters = {adapter.name: adapter for adapter in default_adapters()}
    options = []
    for inventory in analysis.inventory.languages:
        adapter = adapters[inventory.language]
        options.append((adapter, inventory, adapter.launch_info(repo, inventory)))
    if not options:
        return None
    # Prefer a language that knows how to start the app.
    adapter, inventory, launch = next((o for o in options if o[2].command), options[0])
    log.info("Using %s to start the app", inventory.language)
    return adapter, inventory, launch, set(analysis.inventory.env_vars)


def _failed(base: dict, language: str, notes: list[str]) -> BaselineResult:
    for note in notes:
        log.error(note)
    report = BaselineReport(
        **{**base, "language": base.get("language", language)},
        status=BaselineStatus.FAILED,
        notes=notes,
    )
    return BaselineResult(report=report, traces=[], schema={})


def _json_list(items: list) -> str:
    return "[\n" + ",\n".join(item.model_dump_json(indent=2) for item in items) + "\n]"
