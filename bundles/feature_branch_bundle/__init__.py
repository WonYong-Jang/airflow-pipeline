"""Custom Airflow 3 DAG bundles.

The bundle class lives in :mod:`feature_branch_bundle.git_bundle` and is
referenced by its full path in ``dag_bundle_config_list`` (e.g.
``feature_branch_bundle.git_bundle.FeatureBranchGitDagBundle``). We intentionally
do NOT import it here so that importing this package does not pull in Airflow /
the git provider until the bundle is actually instantiated.
"""
