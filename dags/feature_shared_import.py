"""[테스트 2] shared 모듈(common_utils) import → sys.path.append 없이 동작 확인.

common_utils 를 **sys.path 조작 없이** 그대로 import 한다. 번들이 브랜치의 `dags/` 를
파싱 경로로 노출하므로 boilerplate 없이 import 가 해석되어야 한다. common_utils 자체는
수정하지 않고 그대로 사용한다(시나리오 2).

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
