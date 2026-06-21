"""
## Metrics test DAG

StatsD → statsd-exporter → vmagent → Prometheus 파이프라인 검증용 DAG.

외부 의존성 없이 자체 완결적으로 동작하며, 각 task가 약간의 sleep을 가져
`airflow.dag.<dag_id>.<task_id>.duration` 메트릭이 의미 있게 찍히도록 했다.
수동 트리거로 제어할 수 있게 schedule=None 으로 둔다.
"""

from airflow.sdk import dag, task
from pendulum import datetime
import time


@dag(
    start_date=datetime(2025, 1, 1),
    schedule=None,  # 수동 트리거 전용
    catchup=False,
    doc_md=__doc__,
    default_args={"owner": "metrics-test", "retries": 1},
    tags=["metrics", "test"],
)
def metrics_test():
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


metrics_test()
