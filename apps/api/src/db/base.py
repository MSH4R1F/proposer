"""SQLAlchemy declarative base for the proposer DB."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide DeclarativeBase. All ORM models inherit from this."""
