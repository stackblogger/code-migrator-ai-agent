"""What a unit may write, and what counts as "done".

These rules are enforced by code, not by the prompt. A unit can only write its own target
files and its own test file. The files that judge the work are protected.
"""

import re

from migrator.planning.models import FileRole, MigrationUnit

PROTECTED = {"tests/test_skeleton.py", "pyproject.toml", "uv.lock", "app/database.py"}
VALID_PATH = re.compile(r"^(app|tests)/([a-z_][a-z0-9_]*/)*[a-z_][a-z0-9_]*\.py$")
STUB_MARKERS = re.compile(r"MIGRATOR-STUB|status_code=501|not migrated yet", re.IGNORECASE)
SKIPPED_TESTS = re.compile(r"pytest\.(skip|xfail)\b|mark\.(skip|skipif|xfail)\b|unittest\.skip")


def unit_test_path(unit: MigrationUnit) -> str:
    """Tests a unit writes about itself. Test units write their own target instead."""
    return f"tests/generated/test_{unit.id}.py"


def target_files(unit: MigrationUnit) -> list[str]:
    return sorted({f.target for f in unit.files if f.target})


def is_test_unit(unit: MigrationUnit) -> bool:
    return all(f.role == FileRole.TEST for f in unit.files)


def allowed_paths(unit: MigrationUnit) -> list[str]:
    paths = set(target_files(unit))
    if not is_test_unit(unit):
        paths.add(unit_test_path(unit))
    return sorted(paths - PROTECTED)


def check_change(unit: MigrationUnit, contents: dict[str, str]) -> list[str]:
    """Checks before anything is written: paths and syntax (compiled only, never run)."""
    if not contents:
        return ["the answer has no files"]
    allowed = set(allowed_paths(unit))
    problems = []
    for path, content in contents.items():
        if path in PROTECTED or path.startswith(".migrator/"):
            problems.append(f"{path} is protected, it must not be changed")
        elif not VALID_PATH.match(path) or path not in allowed:
            problems.append(
                f"{path} is not allowed for this unit (allowed: {', '.join(sorted(allowed))})"
            )
            continue
        try:
            compile(content, path, "exec")
        except SyntaxError as error:
            problems.append(f"{path}: syntax error on line {error.lineno}: {error.msg}")
        if path.startswith("tests/") and SKIPPED_TESTS.search(content):
            problems.append(f"{path}: skipped or xfail tests are not allowed")
    return problems


def check_done(unit: MigrationUnit, current: dict[str, str]) -> list[str]:
    """Checks after writing: no stubs left in the unit's files, and real tests exist."""
    problems = [
        f"{path} still has a stub (501 / MIGRATOR-STUB / not migrated yet)"
        for path in target_files(unit)
        if path.startswith("app/") and STUB_MARKERS.search(current.get(path, ""))
    ]
    test_paths = target_files(unit) if is_test_unit(unit) else [unit_test_path(unit)]
    for path in test_paths:
        text = current.get(path, "")
        if "def test_" not in text or not ("assert" in text or "raises(" in text):
            problems.append(f"{path} must contain real tests (test functions with asserts)")
    return problems
