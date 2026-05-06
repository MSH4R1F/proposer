"""Import-boundary test for the legal_core leaf-dependency invariant."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator, List, Set, Tuple

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_DIRS = {"tests", "__pycache__"}

FORBIDDEN_TOP_LEVEL = {
    "domain_core",
    "rag_engine",
    "kg_builder",
    "llm_orchestrator",
    "eval",
    "scripts",
}

FORBIDDEN_DOTTED_PREFIXES = {
    "apps.api",
    "apps.web",
    "packages.domain_core",
    "packages.rag_engine",
    "packages.kg_builder",
    "packages.llm_orchestrator",
    "packages.eval",
}


def _python_files() -> Iterator[Path]:
    for path in PACKAGE_ROOT.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in path.relative_to(PACKAGE_ROOT).parts):
            continue
        yield path


def _collect_imports(path: Path) -> List[Tuple[int, str]]:
    """Return list of (lineno, dotted_name) for every Import / ImportFrom."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: List[Tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module is None or (node.level or 0) > 0:
                continue
            out.append((node.lineno, node.module))
    return out


def _violations(path: Path) -> List[str]:
    out: List[str] = []
    for lineno, name in _collect_imports(path):
        top = name.split(".", 1)[0]
        if top in FORBIDDEN_TOP_LEVEL:
            out.append(f"{path}:{lineno} forbidden top-level import {name!r}")
            continue
        for prefix in FORBIDDEN_DOTTED_PREFIXES:
            if name == prefix or name.startswith(prefix + "."):
                out.append(f"{path}:{lineno} forbidden dotted import {name!r}")
                break
    return out


def test_legal_core_is_a_leaf_package():
    all_violations: List[str] = []
    files: Set[Path] = set()
    for f in _python_files():
        files.add(f)
        all_violations.extend(_violations(f))

    assert files, "expected to scan at least one .py file under legal_core/"
    assert not all_violations, (
        "legal_core leaked imports from forbidden packages:\n  "
        + "\n  ".join(all_violations)
    )
