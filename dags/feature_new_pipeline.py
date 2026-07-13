"""[테스트 1] 새 DAG 파일 추가 → 브랜치 네임스페이스 격리 확인.

feature-11946 브랜치에서 새로 추가한 DAG. dag_id 를 prod 에 이미 존재하는
"metrics_test" 와 **일부러 동일**하게 두었다. FeatureBranchGitDagBundle 이
`<브랜치슬러그>__` prefix 를 붙이므로, dev 인스턴스에서는

    feature_11946__metrics_test

로 등장하여 prod 의 `metrics_test` 와 충돌 없이 공존해야 한다.
(sys.path.append 없음, 자체 완결 DAG)
"""

from airflow.sdk import dag, task
from pendulum import datetime


@dag(
    dag_id="metrics_test",  # ← prod 와 동일. prefix 로 충돌 회피되는지 검증용
    start_date=datetime(2025, 1, 1),
    schedule=None,
    catchup=False,
    doc_md=__doc__,
    default_args={"owner": "dev-11946", "retries": 0},
    tags=["test1", "namespace"],
)
def metrics_test():
    @task
    def hello() -> str:
        msg = "feature-11946: new DAG file, isolated by branch prefix"
        print(msg)
        return msg

    hello()


metrics_test()
