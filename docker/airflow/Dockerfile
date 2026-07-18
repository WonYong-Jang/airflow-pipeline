# Custom Airflow image for the FeatureBranchGitDagBundle.
#
# Bakes in:
#   * apache-airflow-providers-git + GitPython — the bundle drives git via
#     GitHook / GitPython.
#   * the feature_branch_bundle package itself — so the bundle classpath is
#     importable (replaces the old bundle-sync PVC delivery).
# structlog already ships with Airflow 3.
#
# Build context = repo ROOT (so `bundles/` is available to COPY):
#   docker build         -t <registry>/airflow-pipeline:3.2.2-git -f docker/airflow/Dockerfile .
#   docker push          <registry>/airflow-pipeline:3.2.2-git
# minikube (single node, no registry):
#   minikube image build -t airflow-pipeline:3.2.2-git -f docker/airflow/Dockerfile .
#   minikube image ls | grep airflow-pipeline
FROM apache/airflow:3.2.2

# apache/airflow:3.2.2 defaults to Python 3.13; override PYTHON_VERSION if you
# pin a different -pythonX.Y base tag.
ARG AIRFLOW_VERSION=3.2.2
ARG PYTHON_VERSION=3.13

# Install with the matching Airflow constraints file so nothing else in the
# image (Airflow core / other providers) gets upgraded or downgraded.
# Runs as the (already active) `airflow` user.
RUN pip install --no-cache-dir \
      "apache-airflow-providers-git" \
      "GitPython" \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

# Bake the bundle package so `feature_branch_bundle.git_bundle.FeatureBranchGitDagBundle`
# resolves without any PYTHONPATH wiring or a PVC sync sidecar.
# --chown=airflow:0 so setuptools can write its egg-info into the copied source
# (the image runs as the non-root `airflow` user; a root-owned COPY would fail).
COPY --chown=airflow:0 bundles /opt/airflow/bundles-src
RUN pip install --no-cache-dir /opt/airflow/bundles-src \
    && rm -rf /opt/airflow/bundles-src
