"""Human readable summary of sandbox runs for the terminal."""

from migrator.sandbox.models import SandboxRun

FAILED_OUTPUT_LINES = 40


def format_runs(runs: list[SandboxRun]) -> str:
    if not runs:
        return "No supported language found, nothing to verify."
    out: list[str] = []
    for run in runs:
        out.append(f"[{run.language}] image: {run.image}")
        for step in run.steps:
            mark = "✓" if step.ok else "✗"
            network = "  (network on)" if step.network else ""
            command = " ".join(step.command)
            out.append(f"  {mark} {step.name:<8} {command:<50} {step.duration_s:>7.1f}s{network}")
        failed = next((s for s in run.steps if not s.ok), None)
        if failed:
            out.append(f"\n  Last {FAILED_OUTPUT_LINES} lines of '{failed.name}' output:")
            lines = failed.output.rstrip().splitlines()[-FAILED_OUTPUT_LINES:]
            out.extend(f"    | {line}" for line in lines)
        out.extend(f"  Note: {note}" for note in run.notes)
        out.append(f"  Result: {run.status.value.upper()}")
        out.append("")
    return "\n".join(out).rstrip()
