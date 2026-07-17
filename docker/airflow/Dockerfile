# minikube (single node, no registry):
# $ minikube image build -t airflow-pipeline:3.2.2-git docker/airflow
# $ minikube image ls | grep airflow-pipeline
FROM apache/airflow:3.2.2

# apache/airflow:3.2.2 defaults to Python 3.12; override PYTHON_VERSION if you
# pin a different -pythonX.Y base tag.
ARG AIRFLOW_VERSION=3.2.2
ARG PYTHON_VERSION=3.12

# Runs as the (already active) `airflow` user; installs into its user site.
RUN pip install --no-cache-dir \
      "apache-airflow-providers-git" \
      "GitPython" \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"
