"""Premium DAG — shared-module import demo.

The helper now lives in the repo-wide ``dags/common_utils`` package. Dev code
imports it as ``from common_utils...``; the feature-branch bundle vendors that
package under each branch's namespace and rewrites the import, so branches stay
isolated while sharing a single source folder.
"""

from airflow.sdk import dag, task
from pendulum import datetime

from common_utils.runtime_variable import runtime_variable


@dag(
    start_date=datetime(2025, 1, 1),
    schedule=None,
    catchup=False,
    doc_md=__doc__,
    default_args={"owner": "kaven", "retries": 1},
    tags=["talk", "premium"],
)
def premium():
    @task
    def show_runtime_variable() -> str:
        value = runtime_variable()
        print(f"runtime_variable() -> {value}")
        return value

    show_runtime_variable()


premium()
