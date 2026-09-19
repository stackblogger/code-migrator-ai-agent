"""Human readable migration plan."""

from migrator.planning.models import MigrationPlan


def format_plan(plan: MigrationPlan) -> str:
    out = [
        f"Migration plan: {plan.source_repo} ({plan.source_language}, "
        f"{', '.join(plan.source_frameworks)}) -> {plan.target}",
        f"  Layout chosen by: {plan.mapped_by}",
        "",
    ]
    for unit in plan.units:
        after = f"  (after {', '.join(unit.depends_on)})" if unit.depends_on else ""
        cycle = "  [import cycle: migrate together]" if len(unit.files) > 1 else ""
        out.append(f"  {unit.id}{after}{cycle}")
        for file in unit.files:
            target = file.target or f"(none: {file.reason})"
            out.append(f"      {file.role.value:<10} {file.source}  ->  {target}")
        out.extend(f"      risk: {risk}" for risk in unit.risks)
    if plan.llm_calls:
        tokens_in = sum(c.usage.input_tokens for c in plan.llm_calls)
        tokens_out = sum(c.usage.output_tokens for c in plan.llm_calls)
        out.append(f"\n  LLM calls: {len(plan.llm_calls)}, tokens in/out: {tokens_in}/{tokens_out}")
    out.extend(f"  Note: {note}" for note in plan.notes)
    return "\n".join(out)
