

from airflow.sdk import dag, task
from pendulum import datetime
import time


@dag(
    start_date=datetime(2025, 1, 1),
    schedule=None,  # 수동 트리거 전용
    catchup=False,
    doc_md=__doc__,
    default_args={"owner": "metrics-test2", "retries": 1},
    tags=["metrics", "test2"],
)
def metrics_test3():
    @task
    def extract() -> int:
        """간단한 추출 단계 — duration 메트릭 생성을 위해 sleep."""
        time.sleep(3)
        return 42

    @task
    def transform(value: int) -> int:
        """변환 단계."""
        time.sleep(2)
        return value * 2

    @task
    def load(value: int) -> None:
        """적재 단계."""
        time.sleep(1)
        print(f"loaded value: {value}")

    load(transform(extract()))


metrics_test3()
