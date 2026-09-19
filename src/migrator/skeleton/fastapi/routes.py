"""FastAPI routes with the same method, path and status code as the source.

Handlers are stubs: they answer 501 until M6 migrates the real logic. Routes that need a
login use `get_current_user`, which fails closed: 401 without a token, 501 with one.
"""

import builtins
import keyword
import re
from collections import defaultdict

from migrator.concepts.keys import snake_case
from migrator.concepts.models import ConceptKind, ConceptModel
from migrator.skeleton.files import FileBuilder

PATH_PARAM = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

AUTH_DEPENDENCY = '''
def get_current_user(authorization: str | None = Header(default=None)):
    """Stub: fails closed. Real token checks are migrated in M6."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing token")
    raise HTTPException(status_code=501, detail="Auth not migrated yet")
'''


def render_auth(model: ConceptModel, targets: dict[str, str | None], files: FileBuilder) -> str:
    guards = [n for n in model.of_kind(ConceptKind.PROVIDER) if n.attributes.get("guard")]
    path = (targets.get(guards[0].file) if guards else None) or "app/auth/dependencies.py"
    files.add(path, AUTH_DEPENDENCY, ["from fastapi import Header, HTTPException"])
    return path.removesuffix(".py").replace("/", ".")


def render_routes(
    model: ConceptModel,
    targets: dict[str, str | None],
    files: FileBuilder,
    schema_modules: dict[str, str],
    auth_module: str,
) -> list[str]:
    """Adds routers; returns their module names (main.py includes them)."""
    by_file = defaultdict(list)
    for route in sorted(model.of_kind(ConceptKind.ROUTE), key=lambda n: (n.file, n.line)):
        by_file[targets.get(route.file) or "app/routes.py"].append(route)

    modules = []
    for path, routes in sorted(by_file.items()):
        imports = {"from fastapi import APIRouter, HTTPException"}
        chunks, used = ["router = APIRouter()"], set()
        for route in routes:
            code, needed = _handler(route, schema_modules, auth_module, used)
            chunks.append(code)
            imports.update(needed)
        files.add(path, "\n\n\n".join(chunks), sorted(imports))
        files.note(
            path, f"Routes from {routes[0].file}. MIGRATOR-STUB: handlers answer 501 until M6."
        )
        modules.append(path.removesuffix(".py").replace("/", "."))
    return modules


def _handler(
    route, schema_modules: dict[str, str], auth_module: str, used: set[str]
) -> tuple[str, set[str]]:
    a = route.attributes
    name = snake_case(route.name.split(".")[-1]).replace("-", "_")
    if keyword.iskeyword(name) or hasattr(builtins, name):
        name += "_route"  # e.g. `list` would hide the Python builtin
    while name in used:
        name += "_"
    used.add(name)
    params, imports = [f"{p}: str" for p in PATH_PARAM.findall(a["path"])], set()
    body = a.get("body")
    if body and body in schema_modules:
        params.append(f"body: {body}")
        imports.add(f"from {schema_modules[body]} import {body}")
    if a["auth"]:
        params.append("user=Depends(get_current_user)")
        imports.update(
            {"from fastapi import Depends", f"from {auth_module} import get_current_user"}
        )
    decorator = f'@router.{a["method"].lower()}("{a["path"]}", status_code={a["status"]})'
    code = (
        f"{decorator}\n"
        f"def {name}({', '.join(params)}):\n"
        f'    raise HTTPException(status_code=501, detail="Not migrated yet: {route.key}")'
    )
    return code, imports
