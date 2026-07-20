"""[테스트 2] repo 공용 모듈(dags/common_utils) import 확인.

helper 를 각 DAG 폴더가 아니라 repo 공용 ``dags/common_utils`` 에 두고 ``from common_utils...``
로 import 한다. 번들이 브랜치별 네임스페이스(``<pkg>``)로 vendoring + import 재작성 하므로,
단일 소스를 공유하면서도 브랜치 간 격리가 유지된다.

dev 인스턴스에서는 feature_11946__shared_import_demo 로 등장하며, 태스크 실행 시
runtime_variable() 값("hello_dags")을 로그로 출력한다.
"""

from airflow.sdk import dag, task
from pendulum import datetime

from common_utils.runtime_variable import runtime_variable


@dag(
    dag_id="shared_import_demo",
    start_date=datetime(2025, 1, 1),
    schedule=None,
    catchup=False,
    doc_md=__doc__,
    default_args={"owner": "dev-11946", "retries": 0},
    tags=["test2", "shared"],
)
def shared_import_demo():
    @task
    def show() -> str:
        value = runtime_variable()
        print(f"feature-11946: runtime_variable() -> {value}")
        return value

    show()


shared_import_demo()
