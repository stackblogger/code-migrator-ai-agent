from migrator.adapters.languages.python.resolver import PythonResolver
from migrator.adapters.languages.typescript.resolver import package_name, resolve_import
from migrator.core.models import ImportRef


def ts(file: str, module: str) -> ImportRef:
    return ImportRef(file=file, module=module, line=1)


def test_typescript_relative_imports():
    files = {"src/a.ts", "src/lib/index.ts", "src/b.tsx", "src/esm.ts"}
    assert resolve_import(ts("src/x.ts", "./a"), files).targets == ["src/a.ts"]
    assert resolve_import(ts("src/x.ts", "./lib"), files).targets == ["src/lib/index.ts"]
    assert resolve_import(ts("src/x.ts", "./b"), files).targets == ["src/b.tsx"]
    assert resolve_import(ts("src/x.ts", "./esm.js"), files).targets == ["src/esm.ts"]
    assert resolve_import(ts("src/x.ts", "./missing"), files).targets == []


def test_typescript_packages():
    assert resolve_import(ts("a.ts", "@nestjs/common"), set()).external_package == "@nestjs/common"
    assert package_name("@scope/pkg/deep/path") == "@scope/pkg"
    assert package_name("lodash/map") == "lodash"
    assert package_name("node:fs") == "fs"


def py(file: str, module: str, names: list[str] | None = None) -> ImportRef:
    return ImportRef(file=file, module=module, names=names or [], line=1)


FILES = {
    "app/__init__.py",
    "app/orders/__init__.py",
    "app/orders/models.py",
    "app/orders/service.py",
    "app/users/models.py",
    "src/lib/util.py",
}


def test_python_absolute_imports():
    r = PythonResolver(FILES)
    assert r.resolve(py("x.py", "app.orders.models")).targets == ["app/orders/models.py"]
    assert r.resolve(py("x.py", "app.orders", ["models", "service"])).targets == [
        "app/orders/models.py",
        "app/orders/service.py",
    ]
    assert r.resolve(py("x.py", "app.orders", ["something"])).targets == ["app/orders/__init__.py"]
    assert r.resolve(py("x.py", "lib.util")).targets == ["src/lib/util.py"]  # src layout


def test_python_relative_imports():
    r = PythonResolver(FILES)
    assert r.resolve(py("app/orders/service.py", ".models", ["Order"])).targets == [
        "app/orders/models.py"
    ]
    assert r.resolve(py("app/orders/service.py", ".", ["models"])).targets == [
        "app/orders/models.py"
    ]
    assert r.resolve(py("app/orders/service.py", "..users.models", ["User"])).targets == [
        "app/users/models.py"
    ]


def test_python_external_vs_unresolved():
    r = PythonResolver(FILES)
    assert r.resolve(py("x.py", "fastapi.routing")).external_package == "fastapi"
    missing = r.resolve(py("x.py", "app.missing"))  # looks internal, so no guessing
    assert missing.targets == [] and missing.external_package is None
