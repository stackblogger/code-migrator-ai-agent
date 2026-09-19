"""Human readable summary of a baseline report for the terminal."""

from migrator.baseline.models import BaselineReport

MAX_LISTED = 10


def format_baseline(report: BaselineReport) -> str:
    out = [
        f"Baseline for {report.repo} ({report.language})",
        f"  Scenarios: {report.scenarios} ({report.holdout_scenarios} held out)",
        f"  Runs:      {report.runs}",
        f"  Rules:     {len(report.rules_applied)} approved normalization rules applied",
    ]
    if report.differences:
        out.append(f"\n  Unstable fields ({len(report.differences)} differences between runs):")
        for d in report.differences[:MAX_LISTED]:
            out.append(f"    - '{d.scenario}' step {d.step}: {d.path}  {d.first!r} vs {d.second!r}")
    if report.proposed_rules:
        out.append("\n  Proposed rules (review them, then pass the approved ones with --rules):")
        for rule in report.proposed_rules:
            out.append(f"    - {rule.path}: {rule.action} ({rule.reason})")

    if report.mutation:
        m = report.mutation
        score = f"{m.score:.0%}" if m.score is not None else "n/a"
        out.append(
            f"\n  Mutation score: {score} "
            f"({m.killed} killed, {m.survived} survived, {m.invalid} did not build)"
        )
        for mutant in [x for x in m.mutants if x.outcome == "survived"][:MAX_LISTED]:
            out.append(
                f"    weak spot: {mutant.file}:{mutant.line}:{mutant.column} "
                f"'{mutant.original}' -> '{mutant.replacement}' was not noticed"
            )

    out.extend(f"  Note: {note}" for note in report.notes)
    out.append(f"\n  Result: {report.status.value.upper()}")
    return "\n".join(out)
