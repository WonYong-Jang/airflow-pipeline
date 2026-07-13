"""Unit tests for the git CLI helpers against a real temp repo (no Airflow)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from feature_branch_bundle import git_cli


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def origin(tmp_path):
    """A bare-ish source repo with main + one feature branch."""
    work = tmp_path / "src"
    work.mkdir()
    _git(["init", "-b", "main"], work)
    _git(["config", "user.email", "t@t"], work)
    _git(["config", "user.name", "t"], work)
    (work / "dags").mkdir()
    (work / "dags" / "a.py").write_text("# DAG a\nfrom airflow import DAG\n")
    _git(["add", "-A"], work)
    _git(["commit", "-m", "init"], work)

    _git(["checkout", "-b", "feature/new"], work)
    (work / "dags" / "b.py").write_text("# DAG b\nfrom airflow import DAG\n")
    _git(["add", "-A"], work)
    _git(["commit", "-m", "add b"], work)
    _git(["checkout", "main"], work)
    return work


def test_mirror_heads_and_diff(tmp_path, origin):
    mirror = tmp_path / "m.git"
    git_cli.clone_mirror(str(origin), mirror)

    heads = git_cli.ls_heads(mirror)
    assert set(heads) == {"main", "feature/new"}

    changed = git_cli.diff_name_only(mirror, "main", "feature/new")
    assert changed == {"dags/b.py"}


def test_export_tree(tmp_path, origin):
    mirror = tmp_path / "m.git"
    git_cli.clone_mirror(str(origin), mirror)

    dest = tmp_path / "out"
    git_cli.export_tree(mirror, "feature/new", dest)
    assert (dest / "dags" / "a.py").exists()
    assert (dest / "dags" / "b.py").exists()
    assert not (dest / ".git").exists()  # clean, no metadata


def test_export_tree_subpath_only(tmp_path, origin):
    """subpath export must include only that dir, not the rest of the repo."""
    # add a non-dags file so we can prove it's excluded
    work = tmp_path / "src"
    (work / "tests").mkdir()
    (work / "tests" / "junk.py").write_text("x = 1\n")
    _git(["add", "-A"], work)
    _git(["commit", "-m", "junk"], work)

    mirror = tmp_path / "m.git"
    git_cli.clone_mirror(str(work), mirror)

    dest = tmp_path / "out"
    git_cli.export_tree(mirror, "main", dest, subpath="dags")
    assert (dest / "dags" / "a.py").exists()
    assert not (dest / "tests").exists()  # excluded ✓


def test_rev_parse(tmp_path, origin):
    mirror = tmp_path / "m.git"
    git_cli.clone_mirror(str(origin), mirror)
    sha = git_cli.rev_parse(mirror, "main")
    assert len(sha) == 40
