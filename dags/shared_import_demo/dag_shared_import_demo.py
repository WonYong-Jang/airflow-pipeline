"""[테스트 2] self-contained DAG 폴더 안의 shared 모듈 import 확인.

DAG 폴더(``dags/shared_import_demo/``) 안에 helper 를 함께 담아 폴더 단위로 복사되어도
import 가 깨지지 않게 한다. 번들이 복사 경로(bundle_path)를 PYTHONPATH 에 올리므로,
폴더명을 앞에 붙인 절대 import 로 해석된다.

dev 인스턴스에서는 feature_11946__shared_import_demo 로 등장하며, 태스크 실행 시
runtime_variable() 값("hello_dags")을 로그로 출력한다.
"""

from airflow.sdk import dag, task
from pendulum import datetime

from shared_import_demo.common_utils.runtime_variable import runtime_variable


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
