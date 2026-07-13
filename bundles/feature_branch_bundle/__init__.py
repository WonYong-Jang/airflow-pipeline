"""Custom Airflow 3 DAG bundles.

The bundle classes live in :mod:`feature_branch_bundle.git_bundle` and are
referenced by their full path in ``dag_bundle_config_list`` (e.g.
``feature_branch_bundle.git_bundle.FeatureBranchGitDagBundle``). We intentionally
do NOT import them here so that the pure-python helpers (``ast_rewrite``,
``git_cli``) can be imported and unit-tested without Airflow installed.
"""
