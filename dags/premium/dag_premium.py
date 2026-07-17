"""Premium DAG — self-contained shared-module import demo.

The helper lives inside this DAG's own folder (``dags/premium/common_utils``) so
the whole folder is copied as one unit by the feature-branch bundle. It is
imported with the folder-qualified path, which resolves because the bundle path
is on PYTHONPATH.
"""

from airflow.sdk import dag, task
from pendulum import datetime

from premium.common_utils.runtime_variable import runtime_variable


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
