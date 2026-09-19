"""Resolve TypeScript import paths to files inside the repo.

Only relative imports ("./x", "../y") are resolved for now. tsconfig `paths`
aliases are not supported yet; they show up as undeclared packages in warnings.
"""

import posixpath

from migrator.core.models import ImportRef

SOURCE_EXTENSIONS = (".ts", ".tsx", ".mts", ".cts", ".d.ts", ".js", ".jsx", ".mjs", ".cjs")

NODE_BUILTINS = frozenset(
    {
        "assert",
        "async_hooks",
        "buffer",
        "child_process",
        "cluster",
        "console",
        "constants",
        "crypto",
        "dgram",
        "diagnostics_channel",
        "dns",
        "domain",
        "events",
        "fs",
        "http",
        "http2",
        "https",
        "inspector",
        "module",
        "net",
        "os",
        "path",
        "perf_hooks",
        "process",
        "punycode",
        "querystring",
        "readline",
        "repl",
        "stream",
        "string_decoder",
        "sys",
        "timers",
        "tls",
        "trace_events",
        "tty",
        "url",
        "util",
        "v8",
        "vm",
        "wasi",
        "worker_threads",
        "zlib",
        "test",
    }
)


def resolve_import(imp: ImportRef, files: set[str]) -> ImportRef:
    if not imp.module.startswith("."):
        return imp.model_copy(update={"external_package": package_name(imp.module)})

    base = posixpath.normpath(posixpath.join(posixpath.dirname(imp.file), imp.module))
    for candidate in _candidates(base):
        if candidate in files:
            return imp.model_copy(update={"targets": [candidate]})
    return imp  # unresolved, analyzer will warn


def package_name(module: str) -> str:
    """Package of a module: `@nestjs/common/x` -> `@nestjs/common`, `lodash/map` -> `lodash`."""
    module = module.removeprefix("node:")
    parts = module.split("/")
    return "/".join(parts[:2]) if module.startswith("@") else parts[0]


def _candidates(base: str) -> list[str]:
    candidates = [base]
    if base.endswith((".js", ".jsx", ".mjs", ".cjs")):  # ESM style: "./x.js" means "./x.ts"
        stem = base.rsplit(".", 1)[0]
        candidates += [stem + ".ts", stem + ".tsx"]
    candidates += [base + ext for ext in SOURCE_EXTENSIONS]
    candidates += [f"{base}/index{ext}" for ext in SOURCE_EXTENSIONS]
    return candidates
