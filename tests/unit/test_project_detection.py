import json

from migrator.adapters.languages import PythonAdapter, TypeScriptAdapter
from migrator.analysis.inventory import env_keys_from_env_files, find_config_files
from migrator.repository import LocalRepository


def test_typescript_package_manager_from_lockfile(make_repo):
    repo = LocalRepository(
        make_repo(
            {
                "package.json": json.dumps(
                    {"dependencies": {"express": "4"}, "devDependencies": {"vitest": "1"}}
                ),
                "pnpm-lock.yaml": "",
                "tsconfig.json": "{}",
            }
        )
    )
    adapter = TypeScriptAdapter()
    manifests = adapter.read_manifests(repo)
    assert manifests[0].package_manager == "pnpm"
    assert adapter.detect_tools(repo, manifests) == {
        "build": ["tsc"],
        "test": ["vitest"],
        "typecheck": ["tsc"],
    }


def test_typescript_package_manager_field_wins(make_repo):
    repo = LocalRepository(
        make_repo({"package.json": json.dumps({"packageManager": "yarn@4.1.0"})})
    )
    assert TypeScriptAdapter().read_manifests(repo)[0].package_manager == "yarn"


def test_python_requirements_and_tools(make_repo):
    repo = LocalRepository(
        make_repo(
            {
                "requirements.txt": "fastapi==0.110  # web\nPyJWT>=2\n-r other.txt\n",
                "requirements-dev.txt": "pytest\nmypy\n",
            }
        )
    )
    adapter = PythonAdapter()
    manifests = adapter.read_manifests(repo)
    main = next(m for m in manifests if m.file == "requirements.txt")
    assert main.dependencies == {"fastapi": "==0.110", "PyJWT": ">=2"}
    assert adapter.detect_tools(repo, manifests) == {"test": ["pytest"], "typecheck": ["mypy"]}
    assert adapter.is_declared("jwt", manifests)  # import name differs from package name
    assert not adapter.is_declared("requests", manifests)


def test_python_poetry_project(make_repo):
    repo = LocalRepository(
        make_repo(
            {
                "pyproject.toml": (
                    "[tool.poetry.dependencies]\npython = '^3.12'\ndjango = '^5'\n"
                    "[tool.poetry.group.dev.dependencies]\npytest = '^8'\n"
                ),
                "poetry.lock": "",
            }
        )
    )
    manifest = PythonAdapter().read_manifests(repo)[0]
    assert manifest.package_manager == "poetry"
    assert manifest.dependencies == {"django": "^5"}
    assert manifest.dev_dependencies == {"pytest": "^8"}


def test_env_files_only_keep_keys(make_repo):
    repo = LocalRepository(
        make_repo({".env.example": "API_KEY=super-secret\nexport PORT=1\n# NOTE=x\n"})
    )
    keys = env_keys_from_env_files(repo, repo.files())
    assert keys == {"API_KEY": [".env.example"], "PORT": [".env.example"]}
    assert "super-secret" not in json.dumps(keys)


def test_config_files():
    files = [
        "src/a.ts",
        "tsconfig.build.json",
        "config/app.yaml",
        "docker-compose.yml",
        "jest.config.ts",
    ]
    assert find_config_files(files) == [
        "tsconfig.build.json",
        "config/app.yaml",
        "docker-compose.yml",
        "jest.config.ts",
    ]
