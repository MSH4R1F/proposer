"""Errors raised by the domain_core package.

These errors are kept narrow and free of dependencies on other packages.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for domain_core errors."""


class DomainNotFoundError(DomainError):
    """Raised when a requested domain id is not registered."""


class DomainConfigError(DomainError):
    """Raised when a YAML domain spec fails validation."""


class DomainGateError(DomainError):
    """Raised when a launch gate artifact is missing, expired, or invalid.

    Concrete signature/freshness checks are deferred to SHA-122; this is the
    type the runtime gate code will raise once that lands.
    """
