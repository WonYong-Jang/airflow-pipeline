"""AST rewriting that namespaces DAGs for a feature branch.

We parse each DAG file and, without executing it, prefix the ``dag_id`` /
``dag_display_name`` with the branch slug and inject branch tags. Two DAG
declaration styles are handled:

* the ``@dag(...)`` TaskFlow decorator (``dag_id`` defaults to the function
  name when omitted, so we inject an explicit prefixed ``dag_id`` in that case);
* the classic ``DAG(dag_id="...")`` / context-manager form.

Doing this at the AST level (rather than string replacement) means we only touch
real keyword arguments and never mangle comments or unrelated identifiers.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ID_KEYS = {"dag_id", "dag_display_name"}
_DAG_CALLS = {"DAG", "dag"}


class _Rewriter(ast.NodeTransformer):
    def __init__(self, prefix: str, extra_tags: list[str]):
        self.prefix = prefix
        self.extra_tags = extra_tags
        self.changed = False

    # --- helpers -----------------------------------------------------------
    def _prefixed(self, value: str) -> str:
        head = f"{self.prefix}__"
        return value if value.startswith(head) else f"{head}{value}"

    def _prefix_constant(self, node: ast.expr) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            new = self._prefixed(node.value)
            if new != node.value:
                node.value = new
                self.changed = True

    def _merge_tags(self, node: ast.expr) -> None:
        if not isinstance(node, ast.List):
            return
        existing = {e.value for e in node.elts if isinstance(e, ast.Constant)}
        for tag in self.extra_tags:
            if tag not in existing:
                node.elts.append(ast.Constant(tag))
                self.changed = True

    def _apply_to_call(self, call: ast.Call) -> None:
        name = getattr(call.func, "id", None) or getattr(call.func, "attr", None)
        if name not in _DAG_CALLS:
            return
        has_tags = False
        for kw in call.keywords:
            if kw.arg in _ID_KEYS:
                self._prefix_constant(kw.value)
            if kw.arg == "tags":
                has_tags = True
                self._merge_tags(kw.value)
        if self.extra_tags and not has_tags:
            call.keywords.append(
                ast.keyword(
                    arg="tags",
                    value=ast.List(
                        elts=[ast.Constant(t) for t in self.extra_tags],
                        ctx=ast.Load(),
                    ),
                )
            )
            self.changed = True

    # --- visitors ----------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        self._apply_to_call(node)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            name = getattr(dec.func, "id", None) or getattr(dec.func, "attr", None)
            if name != "dag":
                continue
            # @dag without an explicit dag_id -> dag_id defaults to the function
            # name at runtime, so inject a prefixed dag_id to avoid colliding
            # with the prod bundle.
            if not any(kw.arg == "dag_id" for kw in dec.keywords):
                dec.keywords.insert(
                    0,
                    ast.keyword(
                        arg="dag_id",
                        value=ast.Constant(self._prefixed(node.name)),
                    ),
                )
                self.changed = True
        return node


def looks_like_dag(source: str) -> bool:
    """Cheap check so we only rewrite/filter files that declare a DAG."""
    return "@dag" in source or "DAG(" in source or "dag(" in source


def rewrite_file(path: Path, prefix: str, extra_tags: list[str]) -> bool:
    """Rewrite a DAG file in place. Returns True if anything changed."""
    source = path.read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    rewriter = _Rewriter(prefix, extra_tags)
    rewriter.visit(tree)
    if rewriter.changed:
        ast.fix_missing_locations(tree)
        path.write_text(ast.unparse(tree))
    return rewriter.changed
