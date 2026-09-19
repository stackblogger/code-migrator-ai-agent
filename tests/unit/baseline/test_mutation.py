from migrator.adapters.languages import PythonAdapter, TypeScriptAdapter
from migrator.baseline.mutation import _apply, find_mutants, pick_mutants


def test_typescript_mutants(tmp_path):
    (tmp_path / "a.ts").write_text(
        "const s = 'a <= b';\nif (x <= 0 && ok === true) { total = a + b; }\n"
    )
    mutants = find_mutants(tmp_path, TypeScriptAdapter(), ["a.ts"])
    swaps = [(m.original, m.replacement) for m in mutants]
    assert swaps == [("<=", ">"), ("&&", "||"), ("===", "!=="), ("true", "false"), ("+", "-")]
    assert all(m.line == 2 for m in mutants)  # nothing from inside the string on line 1


def test_python_mutants(tmp_path):
    (tmp_path / "a.py").write_text("if total <= 0 or flag is True:\n    x = a - b\n")
    mutants = find_mutants(tmp_path, PythonAdapter(), ["a.py"])
    swaps = [(m.original, m.replacement) for m in mutants]
    assert ("<=", ">") in swaps and ("or", "and") in swaps
    assert ("True", "False") in swaps and ("-", "+") in swaps


def test_apply_changes_only_the_token(tmp_path):
    (tmp_path / "a.py").write_text("ok = a <= b\n")
    [mutant] = find_mutants(tmp_path, PythonAdapter(), ["a.py"])
    original = _apply(tmp_path, mutant)
    assert (tmp_path / "a.py").read_text() == "ok = a > b\n"
    assert original == b"ok = a <= b\n"


def test_pick_is_repeatable(tmp_path):
    (tmp_path / "a.py").write_text("x = " + " + ".join(str(i) for i in range(50)) + "\n")
    mutants = find_mutants(tmp_path, PythonAdapter(), ["a.py"])
    assert pick_mutants(mutants, 5) == pick_mutants(mutants, 5)
    assert len(pick_mutants(mutants, 100)) == len(mutants)
