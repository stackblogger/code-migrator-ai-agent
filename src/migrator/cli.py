"""Command line entry point for the `migrator` command."""

import argparse
import json
import sys
from pathlib import Path

from migrator.analysis import CodeGraph, analyze
from migrator.analysis.summary import format_summary
from migrator.baseline import BaselineStatus, create_baseline, write_baseline
from migrator.baseline.summary import format_baseline
from migrator.concepts.extract import build_concept_model
from migrator.concepts.schema_check import check_against_runtime
from migrator.concepts.summary import format_concepts
from migrator.ledger import build_ledger, load_waivers
from migrator.ledger.summary import format_ledger
from migrator.llm import default_client
from migrator.log import setup_logging
from migrator.planning.planner import build_plan
from migrator.planning.summary import format_plan
from migrator.repository import LocalRepository
from migrator.sandbox import DockerSandbox, RunStatus, verify_repo
from migrator.sandbox.summary import format_runs
from migrator.skeleton.check import check_skeleton
from migrator.skeleton.generate import generate_skeleton, write_skeleton


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    setup_logging("DEBUG" if args.verbose else "WARNING" if args.quiet else None)
    try:
        return args.handler(args)
    except (FileNotFoundError, FileExistsError, KeyError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


def _analyze(args: argparse.Namespace) -> int:
    report = analyze(LocalRepository(args.repo))
    if args.out:
        Path(args.out).write_text(report.model_dump_json(indent=2) + "\n")
        print(f"Full report written to {args.out}\n")
    print(format_summary(report))
    return 0


def _deps(args: argparse.Namespace) -> int:
    report = analyze(LocalRepository(args.repo))
    graph = CodeGraph(report.graph.nodes, report.imports)
    if args.reverse:
        found = graph.dependents(args.file, transitive=args.transitive)
        label = "used by"
    else:
        found = graph.dependencies(args.file, transitive=args.transitive)
        label = "depends on"
    print(f"{args.file} {label}:")
    for path in found:
        print(f"  {path}")
    if not found:
        print("  (nothing)")
    return 0


def _verify(args: argparse.Namespace) -> int:
    runs = verify_repo(LocalRepository(args.repo), keep_workspace=args.keep_workspace)
    if args.out:
        data = "[" + ",\n".join(run.model_dump_json(indent=2) for run in runs) + "]\n"
        Path(args.out).write_text(data)
        print(f"Full results written to {args.out}\n")
    print(format_runs(runs))
    all_passed = bool(runs) and all(run.status == RunStatus.PASSED for run in runs)
    return 0 if all_passed else 1


def _baseline(args: argparse.Namespace) -> int:
    result = create_baseline(
        LocalRepository(args.repo),
        Path(args.scenarios),
        rules_path=Path(args.rules) if args.rules else None,
        runs=args.runs,
        mutants=args.mutants,
    )
    write_baseline(result, Path(args.out))
    print(format_baseline(result.report))
    print(f"\nFiles written to {args.out}")
    return 0 if result.report.status == BaselineStatus.STABLE else 1


def _concepts(args: argparse.Namespace) -> int:
    model = build_concept_model(LocalRepository(args.repo))
    if args.out:
        Path(args.out).write_text(model.model_dump_json(indent=2) + "\n")
        print(f"Full concept model written to {args.out}\n")
    print(format_concepts(model))
    if not args.schema:
        return 0
    problems = check_against_runtime(model, json.loads(Path(args.schema).read_text()))
    print(f"\nSchema check against {args.schema}: {len(problems) or 'no'} problems")
    for problem in problems:
        print(f"  - {problem}")
    return 1 if problems else 0


def _ledger(args: argparse.Namespace) -> int:
    source = build_concept_model(LocalRepository(args.source))
    target = build_concept_model(LocalRepository(args.target)) if args.target else None
    waivers = load_waivers(Path(args.waivers) if args.waivers else None)
    ledger = build_ledger(source, target, waivers)
    if args.out:
        Path(args.out).write_text(ledger.model_dump_json(indent=2) + "\n")
        print(f"Full ledger written to {args.out}\n")
    print(format_ledger(ledger))
    return 0 if ledger.complete else 1


def _plan(args: argparse.Namespace) -> int:
    plan = build_plan(
        LocalRepository(args.source), args.target, default_client() if args.llm else None
    )
    if args.out:
        Path(args.out).write_text(plan.model_dump_json(indent=2) + "\n")
        print(f"Plan written to {args.out}\n")
    print(format_plan(plan))
    return 0


def _skeleton(args: argparse.Namespace) -> int:
    repo = LocalRepository(args.source)
    plan = build_plan(repo, args.target, default_client() if args.llm else None)
    skeleton = generate_skeleton(repo, plan)
    out = Path(args.out)
    write_skeleton(skeleton, out, force=args.force)
    print(
        f"Skeleton with {len(skeleton.files)} files written to {out} (layout by {plan.mapped_by})"
    )
    for note in skeleton.notes:
        print(f"  Note: {note}")
    if not args.check:
        return 0
    result = check_skeleton(LocalRepository(out), build_concept_model(repo))
    print(f"\nBoot check: {'PASSED' if result.ok else 'FAILED'}")
    for key, status in result.routes.items():
        print(f"  {key:<28} -> {status}")
    for problem in result.problems:
        print(f"  Problem: {problem}")
    failed = next((s for s in result.build.steps if not s.ok), None) if result.build else None
    if failed:
        print(f"\n  Last lines of '{failed.name}' output:")
        print("\n".join(f"    | {line}" for line in failed.output.rstrip().splitlines()[-25:]))
    return 0 if result.ok else 1


def _cleanup(args: argparse.Namespace) -> int:
    DockerSandbox().cleanup_stale()
    print("Removed leftover sandbox containers (if any).")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="migrator", description="AI code migration agent")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug logs")
    parser.add_argument("-q", "--quiet", action="store_true", help="Show only warnings and errors")
    sub = parser.add_subparsers(required=True)

    analyze_cmd = sub.add_parser("analyze", help="Analyze a repository")
    analyze_cmd.add_argument("repo", help="Path to the repository")
    analyze_cmd.add_argument("--out", help="Write the full JSON report to this file")
    analyze_cmd.set_defaults(handler=_analyze)

    deps_cmd = sub.add_parser("deps", help="Show dependencies of one file")
    deps_cmd.add_argument("repo", help="Path to the repository")
    deps_cmd.add_argument("file", help="Repo-relative file path")
    deps_cmd.add_argument("--reverse", action="store_true", help="Show files that use this file")
    deps_cmd.add_argument("--transitive", action="store_true", help="Include indirect ones")
    deps_cmd.set_defaults(handler=_deps)

    verify_cmd = sub.add_parser("verify", help="Install, build and test a repo in a Docker sandbox")
    verify_cmd.add_argument("repo", help="Path to the repository")
    verify_cmd.add_argument("--out", help="Write full results (with logs) to this JSON file")
    verify_cmd.add_argument(
        "--keep-workspace", action="store_true", help="Do not delete the sandbox copy after run"
    )
    verify_cmd.set_defaults(handler=_verify)

    baseline_cmd = sub.add_parser(
        "baseline", help="Run the app, record traces for scenarios, check they are stable"
    )
    baseline_cmd.add_argument("repo", help="Path to the repository")
    baseline_cmd.add_argument("--scenarios", required=True, help="Scenario suite JSON file")
    baseline_cmd.add_argument("--rules", help="Approved normalization rules JSON file")
    baseline_cmd.add_argument("--out", default="baseline", help="Output folder")
    baseline_cmd.add_argument("--runs", type=int, default=2, help="How many times to replay")
    baseline_cmd.add_argument(
        "--mutants", type=int, default=0, help="Run mutation testing with this many mutants"
    )
    baseline_cmd.set_defaults(handler=_baseline)

    concepts_cmd = sub.add_parser(
        "concepts", help="Show routes, request fields, tables and errors found in the code"
    )
    concepts_cmd.add_argument("repo", help="Path to the repository")
    concepts_cmd.add_argument("--out", help="Write the full concept model to this JSON file")
    concepts_cmd.add_argument(
        "--schema", help="schema.json from `baseline`, to check columns against the real database"
    )
    concepts_cmd.set_defaults(handler=_concepts)

    ledger_cmd = sub.add_parser("ledger", help="Match every source item to the target, or waive it")
    ledger_cmd.add_argument("source", help="Path to the source repository")
    ledger_cmd.add_argument("--target", help="Path to the target repository")
    ledger_cmd.add_argument("--waivers", help="Waivers JSON file (key, reason, approved_by)")
    ledger_cmd.add_argument("--out", help="Write the full ledger to this JSON file")
    ledger_cmd.set_defaults(handler=_ledger)

    plan_cmd = sub.add_parser("plan", help="Order the migration units and pick target files")
    plan_cmd.add_argument("source", help="Path to the source repository")
    plan_cmd.add_argument("--target", default="python-fastapi", help="Target stack")
    plan_cmd.add_argument(
        "--llm", action="store_true", help="Let the LLM (OpenAI) choose the layout"
    )
    plan_cmd.add_argument("--out", help="Write the plan to this JSON file")
    plan_cmd.set_defaults(handler=_plan)

    skeleton_cmd = sub.add_parser(
        "skeleton", help="Generate a target skeleton that builds and boots"
    )
    skeleton_cmd.add_argument("source", help="Path to the source repository")
    skeleton_cmd.add_argument("--out", required=True, help="Folder for the new project")
    skeleton_cmd.add_argument("--target", default="python-fastapi", help="Target stack")
    skeleton_cmd.add_argument(
        "--llm", action="store_true", help="Let the LLM (OpenAI) choose the layout"
    )
    skeleton_cmd.add_argument(
        "--check", action="store_true", help="Build and boot it in the sandbox"
    )
    skeleton_cmd.add_argument("--force", action="store_true", help="Write into a non-empty folder")
    skeleton_cmd.set_defaults(handler=_skeleton)

    cleanup_cmd = sub.add_parser("cleanup", help="Remove leftover sandbox containers")
    cleanup_cmd.set_defaults(handler=_cleanup)
    return parser


if __name__ == "__main__":
    sys.exit(main())
