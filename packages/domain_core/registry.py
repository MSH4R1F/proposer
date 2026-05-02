"""Domain spec registry: load YAML files in ``domain_core/domains/``.

Validates only YAML shape, enum values, ref:// syntax, duplicate IDs, and
filename/id consistency. Does NOT check that referenced files (gold sets,
BM25 indexes, corpus roots, prompt packs) exist on disk - those checks
belong to runtime/eval gate code.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import ValidationError

from domain_core.errors import DomainConfigError, DomainNotFoundError
from domain_core.spec import DomainSpec

_DOMAINS_DIR = Path(__file__).resolve().parent / "domains"


def _expected_filename_stem(domain_id: str) -> str:
    """Map a domain id to the expected YAML filename stem.

    ``housing.deposit.v1`` -> ``housing_deposit_v1``
    """
    return domain_id.replace(".", "_")


def _load_yaml_file(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise DomainConfigError(f"YAML parse error in {path}: {exc}") from exc
    if data is None:
        raise DomainConfigError(f"YAML file is empty: {path}")
    if not isinstance(data, dict):
        raise DomainConfigError(
            f"YAML file {path} must contain a mapping at top level, got {type(data).__name__}"
        )
    return data


def _build_spec(path: Path, data: Dict[str, Any]) -> DomainSpec:
    try:
        return DomainSpec.model_validate(data)
    except ValidationError as exc:
        raise DomainConfigError(
            f"Domain spec validation failed for {path.name}:\n{exc}"
        ) from exc


def _validate_filename_consistency(path: Path, spec: DomainSpec) -> None:
    expected_stem = _expected_filename_stem(str(spec.id))
    if path.stem != expected_stem:
        raise DomainConfigError(
            f"Domain file {path.name} has id {spec.id!r}; "
            f"expected filename stem {expected_stem!r} "
            f"(got {path.stem!r})"
        )


def load_domain_specs(
    domains_dir: Optional[Path] = None,
) -> Dict[str, DomainSpec]:
    """Load all domain YAML files from ``domains_dir``.

    Parameters
    ----------
    domains_dir:
        Override the default search path. Primarily used in tests.

    Returns
    -------
    Mapping of ``DomainSpec.id`` -> ``DomainSpec``.

    Raises
    ------
    DomainConfigError
        If any file fails validation, or if a duplicate id is encountered.
    """
    base = Path(domains_dir) if domains_dir else _DOMAINS_DIR
    if not base.is_dir():
        raise DomainConfigError(f"Domains directory not found: {base}")

    specs: Dict[str, DomainSpec] = {}
    for yaml_path in sorted(base.glob("*.yaml")):
        # Skip dotfiles or example/template files starting with `_`.
        if yaml_path.name.startswith("_") or yaml_path.name.startswith("."):
            continue
        data = _load_yaml_file(yaml_path)
        spec = _build_spec(yaml_path, data)
        _validate_filename_consistency(yaml_path, spec)
        if str(spec.id) in specs:
            raise DomainConfigError(
                f"Duplicate domain id {spec.id!r} found in "
                f"{yaml_path.name}; previously loaded from a sibling file."
            )
        specs[str(spec.id)] = spec
    return specs


@lru_cache(maxsize=1)
def _cached_load() -> Dict[str, DomainSpec]:
    """Cache the default-directory load. Reset via ``_cached_load.cache_clear()``."""
    return load_domain_specs()


def get_domain_spec(domain_id: str) -> DomainSpec:
    """Look up a single ``DomainSpec`` by id, using the default cache."""
    specs = _cached_load()
    if domain_id not in specs:
        raise DomainNotFoundError(
            f"Unknown domain_id {domain_id!r}; "
            f"registered: {sorted(specs.keys())}"
        )
    return specs[domain_id]


def list_domain_specs(stage: Optional[str] = None) -> List[DomainSpec]:
    """List all loaded ``DomainSpec``s, optionally filtered by ``stage``."""
    specs = list(_cached_load().values())
    if stage is None:
        return specs
    return [s for s in specs if s.stage.value == stage]


def reset_cache() -> None:
    """Drop the cached default load. Tests should call this between runs."""
    _cached_load.cache_clear()


# Allow tests / tools to override the domains dir via env var without touching
# the cached default loader.
_ENV_DOMAINS_DIR = "DOMAIN_CORE_DOMAINS_DIR"
if os.environ.get(_ENV_DOMAINS_DIR):
    # Defer to test-time override: clear cache so subsequent calls re-read.
    reset_cache()
