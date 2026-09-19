"""Mutation testing: are our traces strong enough to notice a small bug?

We make one small change in the source code (a "mutant"), for example `<=` to `>` or
`true` to `false`. Then we rebuild, start the app and replay the traces.
If any trace changes, the mutant is "killed" (good). If nothing changes, it "survived",
which means our traces do not check that part of the code (a weak spot).

This works for any language, because it only looks at tree-sitter token types.
"""

import logging
import random
from dataclasses import dataclass
from pathlib import Path

import httpx
from tree_sitter import Node

from migrator.adapters.languages import LanguageAdapter
from migrator.baseline.compare import compare_schemas, compare_traces, normalize_trace
from migrator.baseline.environment import AppEnvironment
from migrator.baseline.models import (
    MutantOutcome,
    MutantResult,
    MutationReport,
    NormalizationRule,
    Scenario,
    Trace,
)
from migrator.baseline.recorder import record_schema, record_suite
from migrator.baseline.runspec import RunSpec
from migrator.core.models import Toolchain
from migrator.sandbox import DockerSandbox, RunStatus
from migrator.sandbox.runner import run_toolchain

log = logging.getLogger(__name__)

OPERATOR_SWAPS = {
    "===": "!==",
    "!==": "===",
    "==": "!=",
    "!=": "==",
    "<": ">=",
    ">=": "<",
    ">": "<=",
    "<=": ">",
    "&&": "||",
    "||": "&&",
    "and": "or",
    "or": "and",
    "+": "-",
    "-": "+",
}
OPERATOR_PARENTS = {
    "binary_expression",
    "comparison_operator",
    "boolean_operator",
    "binary_operator",
}
BOOLEAN_SWAPS = {"true": "false", "false": "true", "True": "False", "False": "True"}


@dataclass(frozen=True)
class Mutant:
    file: str
    start_byte: int
    end_byte: int
    line: int
    column: int
    original: str
    replacement: str

    def describe(self) -> str:
        return f"{self.file}:{self.line}:{self.column} '{self.original}' -> '{self.replacement}'"


def find_mutants(workspace: Path, adapter: LanguageAdapter, files: list[str]) -> list[Mutant]:
    mutants: list[Mutant] = []
    for path in files:
        source = (workspace / path).read_bytes()
        root = adapter.syntax_tree(path, source).root_node
        mutants += [m for node in _walk(root) if (m := _mutant_for(path, node, source))]
    log.info("Found %d possible mutants in %d files", len(mutants), len(files))
    return mutants


def pick_mutants(mutants: list[Mutant], count: int, seed: int = 0) -> list[Mutant]:
    """Same seed gives the same pick, so results can be repeated."""
    chosen = random.Random(seed).sample(mutants, min(count, len(mutants)))
    return sorted(chosen, key=lambda m: (m.file, m.start_byte))


@dataclass
class MutationContext:
    """Everything needed to rebuild, start and replay the app for one mutant."""

    workspace: Path
    toolchain: Toolchain
    spec: RunSpec
    sandbox: DockerSandbox
    scenarios: list[Scenario]
    expected: list[Trace]  # normalized baseline traces
    expected_schema: dict
    rules: list[NormalizationRule]


def run_mutation_testing(mutants: list[Mutant], ctx: MutationContext) -> MutationReport:
    results = []
    for number, mutant in enumerate(mutants, start=1):
        log.info("Mutant %d/%d: %s", number, len(mutants), mutant.describe())
        original = _apply(ctx.workspace, mutant)
        try:
            result = _test_mutant(mutant, ctx)
        finally:
            (ctx.workspace / mutant.file).write_bytes(original)
        log.info("Mutant %d/%d %s: %s", number, len(mutants), result.outcome.upper(), result.detail)
        results.append(result)
    report = _report(results)
    log.info(
        "Mutation score: %s (%d killed, %d survived, %d invalid)",
        report.score,
        report.killed,
        report.survived,
        report.invalid,
    )
    return report


def _test_mutant(mutant: Mutant, ctx: MutationContext) -> MutantResult:
    def result(outcome: MutantOutcome, detail: str) -> MutantResult:
        return MutantResult(
            file=mutant.file,
            line=mutant.line,
            column=mutant.column,
            original=mutant.original,
            replacement=mutant.replacement,
            outcome=outcome,
            detail=detail,
        )

    build = run_toolchain(ctx.toolchain, ctx.workspace, ctx.sandbox, only={"build"})
    if build.status != RunStatus.PASSED:
        return result("invalid", "does not build, so it is not counted")
    try:
        with AppEnvironment(ctx.spec, ctx.workspace, ctx.sandbox) as env:
            schema = record_schema(env)
            traces = record_suite(env, ctx.scenarios)
    except (RuntimeError, httpx.HTTPError) as error:
        return result("killed", f"app failed: {_first_and_last_line(error)}")

    actual = [normalize_trace(t, ctx.rules) for t in traces]
    differences = compare_schemas(ctx.expected_schema, schema) + compare_traces(
        ctx.expected, actual
    )
    if differences:
        first = differences[0]
        return result("killed", f"'{first.scenario}' step {first.step} {first.path} changed")
    return result("survived", "no trace noticed this change")


def _report(results: list[MutantResult]) -> MutationReport:
    killed = sum(r.outcome == "killed" for r in results)
    survived = sum(r.outcome == "survived" for r in results)
    valid = killed + survived
    return MutationReport(
        tested=len(results),
        killed=killed,
        survived=survived,
        invalid=len(results) - valid,
        score=round(killed / valid, 3) if valid else None,
        mutants=results,
    )


def _first_and_last_line(error: Exception) -> str:
    lines = [line.strip() for line in str(error).splitlines() if line.strip()]
    if len(lines) <= 1:
        return lines[0] if lines else type(error).__name__
    return f"{lines[0]} ... {lines[-1]}"


def _mutant_for(path: str, node: Node, source: bytes) -> Mutant | None:
    text = source[node.start_byte : node.end_byte].decode()
    replacement = None
    if node.parent is not None and node.parent.type in OPERATOR_PARENTS:
        replacement = OPERATOR_SWAPS.get(node.type)
    if node.type in ("true", "false"):
        replacement = BOOLEAN_SWAPS.get(text)
    if replacement is None:
        return None
    line, column = node.start_point[0] + 1, node.start_point[1] + 1
    return Mutant(path, node.start_byte, node.end_byte, line, column, text, replacement)


def _apply(workspace: Path, mutant: Mutant) -> bytes:
    file = workspace / mutant.file
    original = file.read_bytes()
    changed = (
        original[: mutant.start_byte] + mutant.replacement.encode() + original[mutant.end_byte :]
    )
    file.write_bytes(changed)
    return original


def _walk(node: Node):
    yield node
    for child in node.children:
        yield from _walk(child)
