"""Import-boundary test for the leaf-dependency invariant.

``packages/domain_core`` must not import any implementation package. This
test walks every ``.py`` file under ``packages/domain_core`` (excluding
``tests``) with the AST module and inspects ``Import`` and ``ImportFrom``
nodes. If any forbidden module is referenced, the test fails.

To sanity-check the test itself, temporarily add e.g. ``import rag_engine``
to a domain_core file and re-run; the test must fail. Revert before
committing.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator, List, Set, Tuple

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_DIRS = {"tests", "__pycache__"}

FORBIDDEN_TOP_LEVEL = {
    "rag_engine",
    "kg_builder",
    "llm_orchestrator",
    "eval",
    "scripts",
}
# Importing apps.api / apps.web is also forbidden. We strip the shared root
# `apps` and check the second segment.
FORBIDDEN_DOTTED_PREFIXES = {
    "apps.api",
    "apps.web",
    "packages.rag_engine",
    "packages.kg_builder",
    "packages.llm_orchestrator",
    "packages.eval",
}


def _python_files() -> Iterator[Path]:
    for path in PACKAGE_ROOT.rglob("*.py"):
        # Skip tests and bytecode caches.
        if any(part in EXCLUDE_DIRS for part in path.relative_to(PACKAGE_ROOT).parts):
            continue
        yield path


def _imports_in_file(path: Path) -> List[Tuple[str, int]]:
    """Return list of (module_name, lineno) for every Import / ImportFrom."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    found: List[Tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            # Treat absolute imports only; relative imports (level > 0)
            # within domain_core are fine.
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


def test_no_forbidden_imports():
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
        "Expected to scan at least one .py file under packages/domain_core"
    )
    assert not offenders, (
        "domain_core must remain a leaf dependency. Forbidden imports:\n  "
        + "\n  ".join(offenders)
    )


def test_forbidden_import_detection_self_check():
    """Sanity-check that the AST scanner can spot a forbidden import.

    Builds a synthetic source string and runs the same logic the test uses,
    then asserts that it would have flagged it. This guards against the
    test silently passing because the AST traversal is broken.
    """
    bad_src = "import rag_engine\nfrom packages.eval.foo import bar\n"
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


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
