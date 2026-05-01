"""Import-boundary test for ``packages/kg_builder/ontology``.

Mirrors ``packages/domain_core/tests/test_import_boundary.py``. The
ontology subpackage may import ``packages/domain_core`` (for shared
enums and forum-profile lookup) but MUST NOT import implementation
packages above it: ``rag_engine``, ``llm_orchestrator``, ``eval``,
``apps.api``, ``apps.web``, or ``scripts``.

To sanity-check this test, temporarily add e.g. ``import rag_engine`` to
a file under ``packages/kg_builder/ontology`` and re-run; it must fail.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator, List, Set, Tuple

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "ontology"
EXCLUDE_DIRS = {"__pycache__"}

FORBIDDEN_TOP_LEVEL = {
    "rag_engine",
    "llm_orchestrator",
    "eval",
    "scripts",
}
FORBIDDEN_DOTTED_PREFIXES = {
    "apps.api",
    "apps.web",
    "packages.rag_engine",
    "packages.llm_orchestrator",
    "packages.eval",
}


def _python_files() -> Iterator[Path]:
    for path in PACKAGE_ROOT.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in path.relative_to(PACKAGE_ROOT).parts):
            continue
        yield path


def _imports_in_file(path: Path) -> List[Tuple[str, int]]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    found: List[Tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.level or 0) == 0:
                found.append((node.module, node.lineno))
    return found


def _is_forbidden(module_name: str) -> bool:
    top = module_name.split(".", 1)[0]
    if top in FORBIDDEN_TOP_LEVEL:
        return True
    for prefix in FORBIDDEN_DOTTED_PREFIXES:
        if module_name == prefix or module_name.startswith(prefix + "."):
            return True
    return False


def test_no_forbidden_imports_in_ontology_subpackage():
    offenders: List[str] = []
    files_scanned = 0
    for path in _python_files():
        files_scanned += 1
        for module_name, lineno in _imports_in_file(path):
            if _is_forbidden(module_name):
                offenders.append(
                    f"{path.relative_to(PACKAGE_ROOT)}:{lineno} -> {module_name}"
                )
    assert files_scanned > 0, (
        "Expected to scan at least one .py file under "
        "packages/kg_builder/ontology"
    )
    assert not offenders, (
        "kg_builder/ontology must remain a leaf-ish module. Forbidden imports:\n  "
        + "\n  ".join(offenders)
    )


def test_forbidden_import_detection_self_check():
    """The AST-walker recognises a forbidden import in a synthetic source."""
    bad_src = (
        "import rag_engine\n"
        "from packages.eval.foo import bar\n"
        "from llm_orchestrator.x import y\n"
    )
    tree = ast.parse(bad_src)
    found_modules: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found_modules.add(node.module)
    forbidden_hits = {m for m in found_modules if _is_forbidden(m)}
    assert "rag_engine" in forbidden_hits
    assert "packages.eval.foo" in forbidden_hits
    assert "llm_orchestrator.x" in forbidden_hits


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
