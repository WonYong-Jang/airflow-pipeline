"""Premium DAG — shared-module import demo.

Imports ``common_utils`` directly with NO ``sys.path`` boilerplate. This works
because the DAG bundle exposes ``<checkout>/dags`` as its parse path, so ``dags/``
is on ``sys.path`` and ``common_utils`` (at ``dags/common_utils``) is importable.
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
