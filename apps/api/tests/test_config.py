import os
from pathlib import Path

import pytest

from apps.api.src.config import APIConfig


def test_database_url_defaults_when_env_missing(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    cfg = APIConfig.from_env()
    assert cfg.database_url == (
        "postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer"
    )


def test_database_url_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:1/d")
    cfg = APIConfig.from_env()
    assert cfg.database_url == "postgresql+asyncpg://u:p@h:1/d"


def test_production_requires_explicit_non_dev_database_url(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="DATABASE_URL"):
        APIConfig.from_env()


def test_production_rejects_local_dev_database_url(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://proposer:proposer-dev@localhost:5432/proposer",
    )

    with pytest.raises(ValueError, match="dev database"):
        APIConfig.from_env()


def test_production_requires_tls_database_url(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://u:p@db.example.com:5432/proposer",
    )

    with pytest.raises(ValueError, match="sslmode"):
        APIConfig.from_env()


def test_production_rejects_debug(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://u:p@db.example.com:5432/proposer?sslmode=require",
    )

    with pytest.raises(ValueError, match="DEBUG"):
        APIConfig.from_env()


# ---------------------------------------------------------------------------
# SHA-20 Phase 8 multi-domain runtime flags
# ---------------------------------------------------------------------------


def test_domain_strict_eval_gates_default_is_true(monkeypatch) -> None:
    monkeypatch.delenv("DOMAIN_STRICT_EVAL_GATES", raising=False)
    cfg = APIConfig.from_env()
    assert cfg.domain_strict_eval_gates is True


def test_domain_strict_eval_gates_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("DOMAIN_STRICT_EVAL_GATES", "false")
    cfg = APIConfig.from_env()
    assert cfg.domain_strict_eval_gates is False


def test_domain_gate_artifact_dir_default(monkeypatch) -> None:
    monkeypatch.delenv("DOMAIN_GATE_ARTIFACT_DIR", raising=False)
    cfg = APIConfig.from_env()
    assert cfg.domain_gate_artifact_dir == Path("data/eval_artifacts/domain_gates")


def test_domain_gate_artifact_dir_env_override(monkeypatch) -> None:
    monkeypatch.setenv("DOMAIN_GATE_ARTIFACT_DIR", "/var/lib/proposer/gates")
    cfg = APIConfig.from_env()
    assert cfg.domain_gate_artifact_dir == Path("/var/lib/proposer/gates")


def test_enabled_domains_csv_parses_with_whitespace(monkeypatch) -> None:
    monkeypatch.setenv(
        "ENABLED_DOMAINS", " housing.deposit.v1 , housing.repairs_social.v1 "
    )
    cfg = APIConfig.from_env()
    assert cfg.enabled_domains == [
        "housing.deposit.v1",
        "housing.repairs_social.v1",
    ]


def test_default_domain_default(monkeypatch) -> None:
    monkeypatch.delenv("DEFAULT_DOMAIN", raising=False)
    monkeypatch.delenv("ENABLED_DOMAINS", raising=False)
    cfg = APIConfig.from_env()
    assert cfg.default_domain == "housing.deposit.v1"


def test_domain_router_enabled_default_false(monkeypatch) -> None:
    monkeypatch.delenv("DOMAIN_ROUTER_ENABLED", raising=False)
    cfg = APIConfig.from_env()
    assert cfg.domain_router_enabled is False


def test_domain_cross_retrieval_default_false(monkeypatch) -> None:
    monkeypatch.delenv("DOMAIN_CROSS_RETRIEVAL_ALLOWED", raising=False)
    cfg = APIConfig.from_env()
    assert cfg.domain_cross_retrieval_allowed is False


def test_domain_beta_allowlist_user_ids_csv(monkeypatch) -> None:
    monkeypatch.setenv("DOMAIN_BETA_ALLOWLIST_USER_IDS", "uid-a, uid-b ,uid-a")
    cfg = APIConfig.from_env()
    assert cfg.domain_beta_allowlist_user_ids == ["uid-a", "uid-b"]


def test_domain_employment_allowlist_csv(monkeypatch) -> None:
    monkeypatch.setenv(
        "DOMAIN_EMPLOYMENT_BETA_ALLOWLIST_USER_IDS", "uid-emp-1,uid-emp-2"
    )
    cfg = APIConfig.from_env()
    assert cfg.domain_employment_beta_allowlist_user_ids == [
        "uid-emp-1",
        "uid-emp-2",
    ]
