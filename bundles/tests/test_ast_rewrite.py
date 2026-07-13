"""Unit tests for the DAG id/tag AST rewriting (no Airflow import needed)."""

from __future__ import annotations

import ast
from pathlib import Path

from feature_branch_bundle.ast_rewrite import looks_like_dag, rewrite_file

PREFIX = "feature_x"
TAGS = ["feature", PREFIX]


def _write(tmp_path: Path, name: str, src: str) -> Path:
    p = tmp_path / name
    p.write_text(src)
    return p


def _dag_kwargs(src: str, call_name: str) -> dict:
    """Extract keyword args of the first ``call_name`` call in ``src``."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name == call_name:
                return {kw.arg: kw.value for kw in node.keywords}
    raise AssertionError(f"no {call_name}() call found")


def test_classic_dag_id_is_prefixed(tmp_path):
    p = _write(
        tmp_path,
        "d.py",
        "from airflow import DAG\n"
        "with DAG(dag_id='my_dag', tags=['team']) as dag:\n    pass\n",
    )
    assert rewrite_file(p, PREFIX, TAGS) is True
    kw = _dag_kwargs(p.read_text(), "DAG")
    assert kw["dag_id"].value == "feature_x__my_dag"
    tags = {e.value for e in kw["tags"].elts}
    assert tags == {"team", "feature", "feature_x"}


def test_taskflow_without_dag_id_gets_injected(tmp_path):
    p = _write(
        tmp_path,
        "d.py",
        "from airflow.sdk import dag\n\n@dag(schedule=None)\ndef my_flow():\n    pass\n",
    )
    assert rewrite_file(p, PREFIX, TAGS) is True
    kw = _dag_kwargs(p.read_text(), "dag")
    assert kw["dag_id"].value == "feature_x__my_flow"
    assert {e.value for e in kw["tags"].elts} == {"feature", "feature_x"}


def test_taskflow_with_explicit_dag_id(tmp_path):
    p = _write(
        tmp_path,
        "d.py",
        "from airflow.sdk import dag\n\n@dag(dag_id='named', tags=['x'])\ndef f():\n    pass\n",
    )
    assert rewrite_file(p, PREFIX, TAGS) is True
    kw = _dag_kwargs(p.read_text(), "dag")
    assert kw["dag_id"].value == "feature_x__named"


def test_idempotent(tmp_path):
    p = _write(
        tmp_path,
        "d.py",
        "from airflow import DAG\nwith DAG(dag_id='a') as d:\n    pass\n",
    )
    assert rewrite_file(p, PREFIX, TAGS) is True
    # second pass: already prefixed + tags present -> no change
    assert rewrite_file(p, PREFIX, TAGS) is False
    assert _dag_kwargs(p.read_text(), "DAG")["dag_id"].value == "feature_x__a"


def test_non_dag_file_untouched(tmp_path):
    src = "VALUE = 1\n\ndef helper():\n    return VALUE\n"
    p = _write(tmp_path, "mod.py", src)
    assert looks_like_dag(src) is False
    assert rewrite_file(p, PREFIX, TAGS) is False
    assert p.read_text() == src
