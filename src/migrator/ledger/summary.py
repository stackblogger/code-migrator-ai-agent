"""Human readable ledger for the terminal."""

from migrator.ledger.models import Ledger, LedgerStatus

ORDER = [LedgerStatus.MISMATCH, LedgerStatus.MISSING, LedgerStatus.WAIVED, LedgerStatus.MAPPED]


def format_ledger(ledger: Ledger) -> str:
    target = ledger.target_repo or "(no target yet)"
    out = [f"Ledger: {ledger.source_repo} -> {target}"]
    counts = ", ".join(f"{ledger.count(s)} {s.value}" for s in ORDER)
    out.append(f"  {len(ledger.rows)} source items: {counts}")

    for status in ORDER:
        rows = [r for r in ledger.rows if r.status == status]
        if not rows:
            continue
        out.append(f"\n  {status.value.upper()}:")
        for row in rows:
            out.append(f"    {row.kind.value:<12} {row.key}")
            details = [*row.differences, row.hint, f"waived: {row.waiver}" if row.waiver else None]
            out.extend(f"{'':17}- {detail}" for detail in details if detail)

    if ledger.extra_in_target:
        out.append("\n  ONLY IN TARGET (check these are wanted):")
        for row in ledger.extra_in_target:
            out.append(f"    {row.kind.value:<12} {row.key}")
    for waiver in ledger.unused_waivers:
        out.append(f"\n  Note: waiver for '{waiver.key}' matches nothing, please remove it")
    out.append(f"\n  Result: {'COMPLETE' if ledger.complete else 'NOT COMPLETE'}")
    return "\n".join(out)
