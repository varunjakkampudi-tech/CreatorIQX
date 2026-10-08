"""Tests for the declarative base and column mixins."""

from __future__ import annotations

from sqlalchemy import Uuid
from sqlalchemy.orm import DeclarativeBase

from creatoriqx_api.platform.db import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionMixin,
)


class _Base(DeclarativeBase):
    pass


class _Example(UUIDPrimaryKeyMixin, TimestampMixin, VersionMixin, SoftDeleteMixin, _Base):
    __tablename__ = "example_mixins"


def test_primary_key_is_uuid_with_callable_default() -> None:
    column = _Example.__table__.c.id
    assert column.primary_key
    assert isinstance(column.type, Uuid)
    assert column.default is not None
    assert column.default.is_callable


def test_timestamp_and_softdelete_columns_exist() -> None:
    columns = _Example.__table__.c
    assert columns.created_at.server_default is not None
    assert columns.updated_at.onupdate is not None
    assert columns.deleted_at.nullable is True


def test_version_column_defaults_to_one() -> None:
    assert _Example.__table__.c.version.default.arg == 1


def test_naming_convention_is_applied_to_base_metadata() -> None:
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"
