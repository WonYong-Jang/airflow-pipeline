"""Airflow 3 DAG bundles backed by the git CLI.

Two bundles are provided and wired up via
``[dag_processor] dag_bundle_config_list`` in airflow.cfg:

* :class:`GitCliDagBundle` — tracks a single ref (used for ``prod`` -> ``main``).
  Supports versioning, so each DAG run pins the exact commit SHA.
* :class:`FeatureBranchGitDagBundle` — one bundle that dynamically discovers all
  branches matching ``branch_prefix``, exports each, prefixes every ``dag_id``
  with the branch slug and tags them, so open feature branches show up in the
  dev instance side by side without colliding with prod DAGs.

Both drive git through :mod:`.git_cli` (see that module for why the CLI).
"""

from __future__ import annotations

import logging
import re
import shutil
import sys
import tempfile
from pathlib import Path

from airflow.dag_processing.bundles.base import BaseDagBundle

from . import git_cli
from .ast_rewrite import looks_like_dag, rewrite_file

log = logging.getLogger(__name__)


def slugify(branch: str) -> str:
    """``feature/new-pipeline`` -> ``feature_new_pipeline`` (safe as an id prefix)."""
    return re.sub(r"[^A-Za-z0-9]+", "_", branch).strip("_")


class GitCliDagBundle(BaseDagBundle):
    """Single-ref git bundle. Exposes ``<checkout>/<subdir>`` as the parse path."""

    supports_versioning = True

    def __init__(
        self,
        *,
        repo_url: str,
        tracking_ref: str = "main",
        subdir: str = "dags",
        **kwargs,
    ) -> None:
        # name / refresh_interval / version are supplied by Airflow's bundle
        # manager and forwarded to BaseDagBundle untouched.
        super().__init__(**kwargs)
        self.repo_url = repo_url
        self.tracking_ref = tracking_ref
        self.subdir = subdir.strip("/")

    # --- storage layout ----------------------------------------------------
    @property
    def _root(self) -> Path:
        try:
            base = Path(self._dag_bundle_root_storage_path)
        except Exception:  # pragma: no cover - fallback when conf unavailable
            base = Path(tempfile.gettempdir()) / "dag_bundles"
        return base / self.name

    @property
    def _mirror(self) -> Path:
        return self._root / "repo.git"

    @property
    def _work(self) -> Path:
        return self._root / "work"

    @property
    def path(self) -> Path:
        return self._work / self.subdir if self.subdir else self._work

    # --- lifecycle ---------------------------------------------------------
    def initialize(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        if not self._mirror.exists():
            git_cli.clone_mirror(self.repo_url, self._mirror)
        super().initialize()
        self._sync()

    def refresh(self) -> None:
        git_cli.fetch(self._mirror)
        self._sync()

    def _sync(self) -> None:
        ref = self.version or self.tracking_ref
        if self._work.exists():
            shutil.rmtree(self._work)
        git_cli.export_tree(self._mirror, ref, self._work)

    def get_current_version(self) -> str | None:
        return git_cli.rev_parse(self._mirror, self.version or self.tracking_ref)

    def view_url(self, version: str | None = None) -> str | None:
        base = self.repo_url[:-4] if self.repo_url.endswith(".git") else self.repo_url
        return f"{base}/tree/{version or self.tracking_ref}"


class FeatureBranchGitDagBundle(GitCliDagBundle):
    """One bundle that tracks every ``branch_prefix`` branch at once.

    On each refresh it exports the full tree of every matching branch under
    ``<root>/branches/<slug>/`` and rewrites the DAG ids to ``<slug>__<id>``.
    The parse path is ``<root>/branches`` (Airflow scans it recursively). Each
    branch's ``subdir`` is added to ``sys.path`` so intra-branch imports such as
    ``from common_utils ... import`` resolve without any ``sys.path`` boilerplate
    inside the DAG files themselves.
    """

    # Multiple branches -> no single commit to pin a run against.
    supports_versioning = False

    def __init__(
        self,
        *,
        repo_url: str,
        base_branch: str = "main",
        branch_prefix: str = "feature/",
        subdir: str = "dags",
        changed_only: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(
            repo_url=repo_url, tracking_ref=base_branch, subdir=subdir, **kwargs
        )
        self.base_branch = base_branch
        self.branch_prefix = branch_prefix
        self.changed_only = changed_only

    @property
    def _out(self) -> Path:
        return self._root / "branches"

    @property
    def path(self) -> Path:
        return self._out

    def get_current_version(self) -> str | None:
        return None

    def _sync(self) -> None:
        out = self._out
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True, exist_ok=True)

        branches = [
            b
            for b in git_cli.ls_heads(self._mirror)
            if b.startswith(self.branch_prefix) and b != self.base_branch
        ]
        log.info("FeatureBranchGitDagBundle: matched branches %s", branches)

        for branch in branches:
            self._materialise_branch(branch, out)

    def _materialise_branch(self, branch: str, out: Path) -> None:
        slug = slugify(branch)
        dest = out / slug
        git_cli.export_tree(self._mirror, branch, dest)

        sub = dest / self.subdir if self.subdir else dest
        if not sub.is_dir():
            log.warning("branch %s has no %r dir, skipping", branch, self.subdir)
            shutil.rmtree(dest, ignore_errors=True)
            return

        changed = (
            git_cli.diff_name_only(self._mirror, self.base_branch, branch)
            if self.changed_only
            else None
        )

        for py in sub.rglob("*.py"):
            source = py.read_text()
            if not looks_like_dag(source):
                # Shared module (e.g. common_utils) — keep as-is so imports work.
                continue
            repo_rel = py.relative_to(dest).as_posix()
            if changed is not None and repo_rel not in changed:
                # Unchanged DAG on this branch — prod already serves it, drop the
                # duplicate so only the branch's actual changes appear.
                py.unlink()
                continue
            rewrite_file(py, prefix=slug, extra_tags=["feature", slug])

        # Make intra-branch imports resolvable during parsing/execution. refresh()
        # runs in the same interpreter that parses these files, so inserting the
        # branch subdir here is enough (last writer wins on identical module names).
        if str(sub) not in sys.path:
            sys.path.insert(0, str(sub))
