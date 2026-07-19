"""Airflow 3 feature-branch DAG bundle backed by the airflow-git provider.

Ported from the Airflow discussion
https://github.com/apache/airflow/discussions/54669 with only light adaptation:

* :class:`FeatureBranchGitDagBundle` tracks every branch matching
  ``branch_prefix`` (e.g. ``feature/``), diffs each against ``base_branch``,
  copies each *changed DAG folder* into Airflow's plugin path and prefixes every
  ``dag_id`` / ``dag_display_name`` with the cleaned branch name so open feature
  branches show up in the dev instance side by side without colliding.

Prerequisites (see the discussion):
  * ``GitPython`` and ``apache-airflow-providers-git`` installed in the image.
  * An Airflow git connection referenced by ``git_conn_id`` for auth.
  * A "one folder == one DAG" repo layout: ``dags/<name>/dag_<name>.py`` (a DAG
    folder is detected by containing a ``dag_*.py`` file).

After Deployment
- git push
- minikube image build -t airflow-pipeline:3.2.2-git -f docker/airflow/Dockerfile .
- kubectl -n airflow rollout restart deploy/airflow-dag-processor
"""

from __future__ import annotations

import ast
import os
import re
import shutil
import tempfile
from contextlib import nullcontext
from pathlib import Path

import git
import structlog
from airflow.dag_processing.bundles.base import BaseDagBundle
from airflow.exceptions import AirflowException
from airflow.providers.git.hooks.git import GitHook

log = structlog.get_logger(__name__)


class FeatureBranchGitDagBundle(BaseDagBundle):
    """
    Custom FeatureBranchGitDagBundle that:
    - Tracks all branches matching a prefix (e.g., "feature/")
    - For each branch, finds DAG folders changed vs base branch (default "main")
    - Copies the full DAG folder into Airflow's bundle path
    - Prefix `dag_id` and `dag_display_name` with the cleaned branch name to avoid collisions
    """

    def __init__(
        self,
        repo_url,
        git_conn_id=None,
        branch_prefix="feature-",
        base_branch="main",
        **kwargs,
    ) -> None:
        """Initialize the FeatureBranchGitDagBundle.

        Args:
            repo_url (str): URL of the Git repository to track.
            git_conn_id (str, optional): Airflow connection ID for Git authentication.
            branch_prefix (str, optional): Prefix for (feature) branches to track. Defaults to "feature/".
            base_branch (str, optional): Name of the base branch to compare changes against. Defaults to "main".
            **kwargs: Additional keyword arguments passed to the BaseDagBundle.
        """
        name = kwargs.pop("name", "feature_branch_bundle")
        super().__init__(name=name, **kwargs)
        self.repo_url = repo_url
        self.git_conn_id = git_conn_id
        self.branch_prefix = branch_prefix
        self.base_branch = base_branch

        # Temporary folder containing the cloned repository
        self.repo_path = Path(tempfile.mkdtemp()) / "repo"
        # We copy our changed DAGs here. This folder must be on PYTHONPATH so the
        # copied DAG packages (and their in-folder helpers) are importable — see
        # the PYTHONPATH env in the Helm values.
        self.bundle_path = Path("/opt/airflow/bundle_folders")

        self._repo = None

        self._log = log.bind(
            bundle_name=self.name,
            version=self.version,
            repo_path=self.repo_path,
            versions_path=self.versions_dir,
            git_conn_id=self.git_conn_id,
        )

        self._log.debug("Reached FeatureBranchGitDagBundle __init__")

        self.hook: GitHook | None = None
        try:
            if self.git_conn_id:
                self.hook = GitHook(git_conn_id=self.git_conn_id, repo_url=self.repo_url)
                if self.hook.repo_url:
                    # GitHook may rewrite repo_url (e.g., injecting credentials)
                    self.repo_url = self.hook.repo_url
        except Exception as e:
            self._log.warning("Could not create GitHook", conn_id=git_conn_id, exc=e)

    @property
    def path(self) -> Path:
        """
        Airflow looks here for DAG files
        """
        return self.bundle_path

    def initialize(self):
        """
        Clone or open the repository
        """
        if not self.repo_url:
            raise AirflowException(f"Connection {self.git_conn_id} doesn't have a host url")
        self._log.info("Initialize FeatureBranchGitDagBundle")
        with self.lock():
            cm = self.hook.configure_hook_env() if self.hook else nullcontext()
            with cm:
                self.repo_path.parent.mkdir(parents=True, exist_ok=True)
                if not self.repo_path.exists():
                    self._repo = git.Repo.clone_from(
                        self.repo_url, self.repo_path, branch=self.base_branch
                    )
                else:
                    self._repo = git.Repo(self.repo_path)

            self.repo_path.mkdir(parents=True, exist_ok=True)
            self.bundle_path.mkdir(parents=True, exist_ok=True)
        # self.refresh()

    def get_current_version(self) -> str:
        """
        Return a dict of branch:commit_sha as the "version"
        """
        versions = {}
        for ref in self._repo.remotes.origin.refs:
            short = ref.remote_head  # "feature-11946" (strip the origin/ prefix)
            if short != "HEAD" and short.startswith(self.branch_prefix):
                versions[short] = ref.commit.hexsha
        return str(versions)

    def refresh(self) -> bool:
        """
        Pull latest changes and rebuild bundle contents
        """
        self._log.info("Refresh FeatureBranchGitDagBundle Start")
        with self.lock():

            # Cleanup old bundle
            # Current method: Full Rebuild, not Incremental Update..
            # TODO: Need to Check
            if self.bundle_path.exists():
                shutil.rmtree(self.bundle_path)
            self.bundle_path.mkdir(parents=True, exist_ok=True)

            # self._log.info("bundle_path rm sleep...")
            # import time
            # time.sleep(20) # for test

            # Fetch all branches
            cm = self.hook.configure_hook_env() if self.hook else nullcontext()
            with cm:
                self._repo.git.fetch("--all")
                self._repo.git.clean("-xdf")
                self._repo.git.checkout(self.base_branch)
                self._repo.git.reset("--hard", f"origin/{self.base_branch}")

            for ref in self._repo.remotes.origin.refs:
                self._log.info(f"Target Ref: {ref}")
                # remote refs are named "origin/<branch>"; strip the remote so the
                # prefix filter and the id prefix use the clean branch name.
                short = ref.remote_head  # e.g. "feature-11946"
                # Only consider branches with the given prefix
                if short == "HEAD" or not short.startswith(self.branch_prefix):
                    continue

                # Clean branch name for use as prefix (short -> no "origin_" in dag_id)
                branch_name = re.sub(r"[^A-Za-z0-9_\-\.]", "_", short)  # safe prefix

                # Checkout the branch (ref.name = "origin/<branch>"; detached, read-only)
                self._repo.git.clean("-xdf")
                self._repo.git.checkout(ref.name)

                # Get changed files vs base_branch
                diff_files = self._repo.git.diff(
                    f"{self.base_branch}...{ref.name}", name_only=True
                ).splitlines()
                self._log.debug(
                    f"Diff_Files: {diff_files}", branch=ref.name, diff_files=diff_files
                )

                # Detect DAG folders (top-level folder containing dag_*.py)
                # We expect all related file of one DAG to be in a single folder, where dag_*.py is located at root level
                changed_dag_folders = set()
                for file_path in diff_files:
                    self._log.debug(f"File_Path: {file_path}")
                    path = Path(file_path)
                    if path.suffix != ".py":
                        continue
                    if "__init__.py" in str(path):
                        continue
                    dag_root = self._find_dag_root(path)
                    if dag_root:
                        self._log.debug(f"Dag_Root: {dag_root}")
                        changed_dag_folders.add(dag_root)
                    else:
                        self._log.debug("No Dag Root found!")

                # Copy each changed DAG folder into bundle
                self._log.info(f"Changed Dag folders: {changed_dag_folders}")
                for dag_root in changed_dag_folders:
                    self._log.debug(f"Dag root: {dag_root}")

                    # Copy entire folder
                    src = self.repo_path / "dags" / f"{dag_root}"
                    dst = self.bundle_path / f"{dag_root}"
                    if dst.exists():
                        self._log.warning(
                            f"DAG folder {dag_root} already exists - possibly modified in multiple feature branches. Overwriting.",
                            dag_root=str(dag_root),
                            branch=ref.name,
                            dst_path=str(dst),
                        )
                    shutil.copytree(src, dst, dirs_exist_ok=True)

                    # Walk through all directories and subdirectories and ensure __init__.py exists
                    for dirpath, _, _ in os.walk(self.bundle_path):
                        # Construct the path for the __init__.py file
                        init_file = Path(dirpath) / "__init__.py"

                        # Create the file if it doesn't exist
                        self._log.debug(f"Ensuring {init_file} exists...")
                        init_file.touch()

                    # Rewrite `dag_id` and `dag_display_name` in copied files to avoid collisions
                    # Add specific tag (e.g., `feature` tag if feature in branch name; `dev` tag if dev in branch name)
                    for pyfile in dst.rglob("*.py"):
                        self.rewrite_dag_file(pyfile, branch_name)
                    self._log.debug("Finished rewriting.")
            self._log.info(f"Finished refreshing bundle at {self.bundle_path}")
            return True

    def _find_dag_root(self, file_path: Path) -> Path:
        """
        Walk up from the file until we find a folder containing dag_*.py
        Returns relative path to 'dags/' folder
        """
        repo_dags_root = self.repo_path / "dags"
        full_path = self.repo_path / file_path
        for parent in full_path.parents:
            if parent == repo_dags_root:
                break
            if not parent.exists():
                continue  # skip missing directories
            if any(
                f.name.startswith("dag_") and f.suffix == ".py" for f in parent.iterdir()
            ):
                return parent.relative_to(repo_dags_root)
        return None

    def rewrite_dag_file(self, path: Path, branch_name: str):
        """Rewrite `dag_id` and `dag_display_name` in a single file by prefixing with branch_name.
        Add specific tag to the tags list (e.g., `feature` tag if feature in branch name; `dev` tag if dev in branch name).
        """
        branch_name = re.sub(r"[^A-Za-z0-9_\-\.]", "_", branch_name)

        with open(path) as f:
            source = f.read()

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            self._log.debug(f"Skipping {path}, failed to parse: {e}")
            return

        prefixer = RewriteDag(branch_name)
        new_tree = prefixer.visit(tree)
        new_code = ast.unparse(new_tree)

        with open(path, "w") as f:
            f.write(new_code)


class RewriteDag(ast.NodeTransformer):
    """AST transformer to rewrite dag_id and dag_display_name by prefixing with branch name.
    Furthermore, it adds specific tag to the tags list (e.g., `feature` tag if feature in branch name; `dev` tag if dev in branch name).
    """

    def __init__(self, prefix: str):
        """Initialize with the prefix to add.

        Args:
            prefix (str): The prefix to add to dag_id and dag_display_name.
        """
        self.prefix = prefix
        if "feature" in self.prefix:
            self.tag = "feature"
        elif "dev" in self.prefix:
            self.tag = "dev"
        else:
            self.tag = "from_branch"

    def _prefix_kw(self, kw: ast.keyword):
        """Helper to prefix dag_id or dag_display_name"""
        if isinstance(kw.value, ast.Constant) and not kw.value.value.startswith(
            f"{self.prefix}__"
        ):
            kw.value.value = f"{self.prefix}__{kw.value.value}"

    def _add_feature_tag(self, node: ast.Call):
        """Add 'feature' to tags if not already present"""
        for kw in node.keywords:
            if kw.arg == "tags":
                if isinstance(kw.value, ast.List):
                    # Only add if not already present
                    existing_tags = {
                        elt.value for elt in kw.value.elts if isinstance(elt, ast.Constant)
                    }
                    if self.tag not in existing_tags:
                        kw.value.elts.append(ast.Constant(value=self.tag))
                return
        # If no tags keyword, add it
        node.keywords.append(
            ast.keyword(
                arg="tags",
                value=ast.List(elts=[ast.Constant(value=self.tag)], ctx=ast.Load()),
            )
        )

    def visit_Call(self, node: ast.Call):
        # Handle DAG(...) calls
        if getattr(node.func, "id", None) == "DAG":
            for kw in node.keywords:
                if kw.arg in {"dag_id", "dag_display_name"}:
                    self._prefix_kw(kw)
            self._add_feature_tag(node)
        return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Handle @dag(...) decorators
        new_decorators = []
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and getattr(dec.func, "id", None) == "dag":
                for kw in dec.keywords:
                    if kw.arg in {"dag_id", "dag_display_name"}:
                        self._prefix_kw(kw)
                self._add_feature_tag(dec)
            new_decorators.append(dec)
        node.decorator_list = new_decorators
        return self.generic_visit(node)
