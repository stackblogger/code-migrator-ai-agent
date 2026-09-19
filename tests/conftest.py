import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"


@pytest.fixture
def make_repo(tmp_path: Path):
    """Create a small repo on disk from a {path: content} dict."""

    def _make(files: dict[str, str]) -> Path:
        for rel, content in files.items():
            path = tmp_path / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return tmp_path

    return _make


def assert_snapshot(name: str, data: dict) -> None:
    """Compare with tests/snapshots/<name>.json. Run with UPDATE_SNAPSHOTS=1 to refresh."""
    path = SNAPSHOTS / f"{name}.json"
    actual = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_SNAPSHOTS") == "1" or not path.exists():
        path.write_text(actual)
        return
    assert json.loads(path.read_text()) == json.loads(actual), (
        f"Snapshot {name} changed. If this is expected, run: UPDATE_SNAPSHOTS=1 pytest"
    )
