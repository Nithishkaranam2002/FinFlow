"""Shared SQLAlchemy helpers."""

from enum import Enum as PyEnum
from typing import TypeVar

from sqlalchemy import Enum

E = TypeVar("E", bound=PyEnum)


def pg_enum(enum_cls: type[E], name: str) -> Enum:
    """PostgreSQL enum column that persists enum values, not member names."""
    return Enum(
        enum_cls,
        name=name,
        values_callable=lambda members: [member.value for member in members],
    )
