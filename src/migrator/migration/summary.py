"""Human readable migration progress."""

from migrator.migration.models import MigrationState, UnitStatus
from migrator.planning.models import MigrationPlan

MARKS = {
    UnitStatus.GREEN: "✓",
    UnitStatus.BLOCKED: "✗",
    UnitStatus.SKIPPED: "-",
    UnitStatus.PENDING: "○",
}


def green_ratio(state: MigrationState) -> float | None:
    """Green units out of units that had real work (skipped ones do not count)."""
    worked = [u for u in state.units.values() if u.status in (UnitStatus.GREEN, UnitStatus.BLOCKED)]
    return sum(u.status == UnitStatus.GREEN for u in worked) / len(worked) if worked else None


def format_migration(plan: MigrationPlan, state: MigrationState) -> str:
    out = [f"Migration of {plan.source_repo} -> {plan.target}", ""]
    tokens_in = tokens_out = 0
    for unit in plan.units:
        unit_state = state.units.get(unit.id)
        status = unit_state.status if unit_state else UnitStatus.PENDING
        sources = ", ".join(f.source for f in unit.files)
        attempts = (
            f"  ({len(unit_state.attempts)} attempt(s))"
            if unit_state and unit_state.attempts
            else ""
        )
        out.append(f"  {MARKS[status]} {unit.id} {status.value:<8} {sources}{attempts}")
        if unit_state and status == UnitStatus.BLOCKED:
            last = unit_state.attempts[-1] if unit_state.attempts else None
            if last:
                out.append(f"      last failure at {last.stage}: {last.error}")
            out.append(f"      report: .migrator/blocked/{unit.id}.md")
        for attempt in unit_state.attempts if unit_state else []:
            tokens_in += attempt.input_tokens
            tokens_out += attempt.output_tokens

    statuses = [
        state.units[u.id].status if u.id in state.units else UnitStatus.PENDING for u in plan.units
    ]
    counts = {status: statuses.count(status) for status in UnitStatus}
    ratio = green_ratio(state)
    rate = f"{ratio:.0%}" if ratio is not None else "n/a"
    out += [
        "",
        "  " + ", ".join(f"{status.value}: {counts[status]}" for status in UnitStatus),
        f"  Green rate (of units with work): {rate}",
        f"  LLM tokens in/out: {tokens_in}/{tokens_out}",
    ]
    return "\n".join(out)
