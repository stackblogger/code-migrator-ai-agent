"""Human readable summary of a RepoReport for the terminal."""

from migrator.core.models import RepoReport


def format_summary(report: RepoReport) -> str:
    inv = report.inventory
    out = [f"Repository: {inv.repo_name} ({inv.total_files} files)", ""]

    for lang in inv.languages:
        managers = sorted({m.package_manager for m in lang.manifests}) or ["none"]
        out.append(f"[{lang.language}]")
        out.append(f"  Source files:    {len(lang.source_files)}")
        out.append(f"  Test files:      {len(lang.test_files)}")
        out.append(f"  Package manager: {', '.join(managers)}")
        for category, tools in lang.tools.items():
            out.append(f"  {category.capitalize() + ':':<16} {', '.join(tools)}")
        out.append(f"  Entry points:    {', '.join(lang.entry_points) or 'none found'}")
        out.append(f"  Packages used:   {len(lang.external_packages)}")
        out.append("")

    internal = sum(1 for i in report.imports if i.targets)
    out.append(f"Symbols: {len(report.symbols)}")
    out.append(f"Imports: {len(report.imports)} ({internal} inside repo)")
    out.append(f"Env vars: {', '.join(inv.env_vars) or 'none'}")
    out.append(f"Config files: {len(inv.config_files)}")
    out.append("")

    out.append(f"Cycles: {len(report.graph.cycles)}")
    for group in report.graph.cycles:
        out.append("  - " + " <-> ".join(group))
    out.append("")

    out.append("Migration order (dependencies first):")
    for step, group in enumerate(report.graph.migration_order, start=1):
        out.append(f"  {step:>3}. {' + '.join(group)}")
    out.append("")

    out.append(f"Warnings: {len(report.warnings) or 'none'}")
    out.extend(f"  - {w}" for w in report.warnings)
    return "\n".join(out)
