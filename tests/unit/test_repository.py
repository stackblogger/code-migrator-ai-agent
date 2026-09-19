import pytest

from migrator.repository import LocalRepository, UnsafePathError


def test_lists_files_and_skips_vendor_folders(make_repo):
    root = make_repo(
        {
            "src/a.ts": "",
            "node_modules/x/index.js": "",
            ".git/config": "",
            "app/__pycache__/a.pyc": "",
            "README.md": "",
        }
    )
    assert LocalRepository(root).files() == ["README.md", "src/a.ts"]


def test_rejects_paths_outside_repo(make_repo):
    repo = LocalRepository(make_repo({"a.txt": "hi"}))
    assert repo.read_text("a.txt") == "hi"
    with pytest.raises(UnsafePathError):
        repo.read_text("../../etc/passwd")


def test_skips_symlinks(make_repo, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "secret.txt"
    outside.write_text("secret")
    root = make_repo({"a.txt": ""})
    (root / "link.txt").symlink_to(outside)
    assert LocalRepository(root).files() == ["a.txt"]


def test_missing_folder():
    with pytest.raises(FileNotFoundError):
        LocalRepository("/does/not/exist")
