"""Boot check: the skeleton must build, pass its smoke test, start, and have every route.

Every route is called once without a token:
- a route that needs login in the source must answer 401 (auth is enforced, fails closed)
- an open route must answer 422 (validation ran) or 501 (stub reached)
404 or 405 means the route is missing. Anything else is reported as a problem.
"""

import logging
import re
from dataclasses import dataclass, field

import httpx

from migrator.adapters.languages import PythonAdapter
from migrator.analysis import analyze
from migrator.baseline.environment import AppEnvironment
from migrator.baseline.runspec import build_run_spec
from migrator.concepts.models import ConceptKind, ConceptModel
from migrator.repository import LocalRepository
from migrator.sandbox import DockerSandbox, RunStatus, SandboxRun
from migrator.sandbox.runner import run_toolchain
from migrator.sandbox.workspace import Workspace

log = logging.getLogger(__name__)

OPEN_ROUTE_OK = {422, 501}
PATH_PARAM = re.compile(r"\{[^}]+\}")


@dataclass
class SkeletonCheck:
    ok: bool
    build: SandboxRun | None = None
    routes: dict[str, int] = field(default_factory=dict)  # route key -> status we got
    problems: list[str] = field(default_factory=list)


def check_skeleton(
    skeleton_repo: LocalRepository,
    source_concepts: ConceptModel,
    sandbox: DockerSandbox | None = None,
) -> SkeletonCheck:
    sandbox = sandbox or DockerSandbox()
    adapter = PythonAdapter()
    report = analyze(skeleton_repo, [adapter])
    [inventory] = report.inventory.languages
    toolchain = adapter.toolchain(skeleton_repo, inventory)
    launch = adapter.launch_info(skeleton_repo, inventory)
    spec = build_run_spec(skeleton_repo, toolchain, launch, set(report.inventory.env_vars), {})

    with Workspace(skeleton_repo) as workspace:
        build = run_toolchain(toolchain, workspace.path, sandbox)
        _keep_lockfile(workspace.path, skeleton_repo)
        if build.status != RunStatus.PASSED:
            return SkeletonCheck(
                ok=False, build=build, problems=[f"build: {build.status}", *build.notes]
            )
        try:
            with AppEnvironment(spec, workspace.path, sandbox) as env:
                statuses = _probe_routes(env.base_url, source_concepts)
        except (RuntimeError, httpx.HTTPError) as error:
            return SkeletonCheck(ok=False, build=build, problems=[f"app did not start: {error}"])

    problems = []
    for route in source_concepts.of_kind(ConceptKind.ROUTE):
        status = statuses[route.key]
        if route.attributes["auth"] and status != 401:
            problems.append(
                f"{route.key}: needs login in source, but answered {status} without a token"
            )
        elif not route.attributes["auth"] and status not in OPEN_ROUTE_OK:
            problems.append(
                f"{route.key}: answered {status}, expected one of {sorted(OPEN_ROUTE_OK)}"
            )
    for problem in problems:
        log.error("Skeleton route check: %s", problem)
    log.info("Skeleton check: %d routes probed, %d problems", len(statuses), len(problems))
    return SkeletonCheck(ok=not problems, build=build, routes=statuses, problems=problems)


def _keep_lockfile(workspace, skeleton_repo: LocalRepository) -> None:
    """Copy the uv.lock made during install back, so the next install is frozen."""
    lockfile = workspace / "uv.lock"
    if lockfile.exists() and not skeleton_repo.exists("uv.lock"):
        (skeleton_repo.root / "uv.lock").write_bytes(lockfile.read_bytes())
        log.info("Saved uv.lock into the skeleton, future installs will be repeatable")


def _probe_routes(base_url: str, concepts: ConceptModel) -> dict[str, int]:
    statuses = {}
    with httpx.Client(base_url=base_url, timeout=30) as client:
        for route in concepts.of_kind(ConceptKind.ROUTE):
            path = PATH_PARAM.sub("1", route.attributes["path"])
            body = {} if route.attributes.get("body") else None
            response = client.request(route.attributes["method"], path, json=body)
            statuses[route.key] = response.status_code
            log.info("Probe %s %s -> %d", route.attributes["method"], path, response.status_code)
    return statuses
