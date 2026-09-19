"""Command line entry point for the `migrator` command."""

import argparse
import sys
from pathlib import Path

from migrator.analysis import CodeGraph, analyze
from migrator.analysis.summary import format_summary
from migrator.baseline import BaselineStatus, create_baseline, write_baseline
from migrator.baseline.summary import format_baseline
from migrator.log import setup_logging
from migrator.repository import LocalRepository
from migrator.sandbox import DockerSandbox, RunStatus, verify_repo
from migrator.sandbox.summary import format_runs


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    setup_logging("DEBUG" if args.verbose else "WARNING" if args.quiet else None)
    try:
        return args.handler(args)
    except (FileNotFoundError, KeyError, RuntimeError, ValueError) as error:
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

    cleanup_cmd = sub.add_parser("cleanup", help="Remove leftover sandbox containers")
    cleanup_cmd.set_defaults(handler=_cleanup)
    return parser


if __name__ == "__main__":
    sys.exit(main())
