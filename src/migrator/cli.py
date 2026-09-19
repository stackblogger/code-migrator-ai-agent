"""Command line entry point: `migrator analyze <repo>` and `migrator deps <repo> <file>`."""

import argparse
import sys
from pathlib import Path

from migrator.analysis import CodeGraph, analyze
from migrator.analysis.summary import format_summary
from migrator.repository import LocalRepository


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except (FileNotFoundError, KeyError) as error:
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="migrator", description="AI code migration agent")
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
    return parser


if __name__ == "__main__":
    sys.exit(main())
