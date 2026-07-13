"""git CLI wrappers used by the DAG bundles.

We drive git through the CLI (subprocess) rather than the airflow-git provider /
GitPython so the bundle stays self-contained and works against a public repo
without configuring an Airflow git connection. The image only needs `git` and
`tar`, both already present in the apache/airflow base image.

Everything is built around a single ``--mirror`` clone (a bare repo that mirrors
all remote heads). Trees are materialised with ``git archive`` piped into
``tar``, which gives a clean checkout with no ``.git`` metadata.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def clone_mirror(repo_url: str, dest: Path) -> None:
    """Create a mirror (bare) clone at ``dest`` if it does not exist yet."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    _git(["clone", "--mirror", repo_url, str(dest)])


def fetch(mirror: Path) -> None:
    """Refresh all heads on an existing mirror clone."""
    _git(["fetch", "--prune", "origin", "+refs/heads/*:refs/heads/*"], cwd=mirror)


def ls_heads(mirror: Path) -> list[str]:
    """Return the short names of all local heads in the mirror."""
    out = _git(["for-each-ref", "--format=%(refname:short)", "refs/heads"], cwd=mirror)
    return [line for line in out.splitlines() if line]


def rev_parse(mirror: Path, ref: str) -> str:
    """Resolve ``ref`` to a full commit SHA."""
    return _git(["rev-parse", ref], cwd=mirror)


def diff_name_only(mirror: Path, base_ref: str, ref: str) -> set[str]:
    """Repo-relative paths changed on ``ref`` since it diverged from ``base_ref``.

    Uses the three-dot form (merge-base diff) so we only see what the branch
    actually added, not unrelated commits that landed on base afterwards.
    """
    out = _git(["diff", "--name-only", f"{base_ref}...{ref}"], cwd=mirror)
    return {line for line in out.splitlines() if line}


def export_tree(mirror: Path, ref: str, dest: Path) -> None:
    """Materialise the full tree of ``ref`` into ``dest`` (no .git metadata)."""
    dest.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(
        ["git", "archive", ref],
        cwd=str(mirror),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["tar", "-x", "-C", str(dest)],
        input=archive.stdout,
        check=True,
    )
