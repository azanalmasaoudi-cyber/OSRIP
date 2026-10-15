import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import ARRAY, Boolean, ForeignKey, Identity, Integer, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.enums import PhysicalDimension, Section, ValueType
from app.models.types import AREA_LEVEL, PHYSICAL_DIMENSION, SECTION, VALUE_TYPE

UUID_PK = {"primary_key": True, "server_default": text("gen_random_uuid()")}


class Unit(Base):
    __tablename__ = "unit"

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    code: Mapped[str] = mapped_column(Text, unique=True)
    dimension: Mapped[PhysicalDimension] = mapped_column(PHYSICAL_DIMENSION)
    label_en: Mapped[str] = mapped_column(Text)
    label_ar: Mapped[str] = mapped_column(Text)


class Indicator(Base):
    __tablename__ = "indicator"

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    code: Mapped[str] = mapped_column(Text, unique=True)
    section: Mapped[Section] = mapped_column(SECTION)
    measure: Mapped[str] = mapped_column(Text)
    dimension: Mapped[PhysicalDimension] = mapped_column(PHYSICAL_DIMENSION)
    value_type: Mapped[ValueType] = mapped_column(VALUE_TYPE)
    requires_commodity: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    requires_partner: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    requires_flow: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    name_en: Mapped[str] = mapped_column(Text)
    name_ar: Mapped[str] = mapped_column(Text)
    definition_en: Mapped[str] = mapped_column(Text)
    definition_ar: Mapped[str] = mapped_column(Text)
    limitation_en: Mapped[str] = mapped_column(Text, server_default=text("''"))
    limitation_ar: Mapped[str] = mapped_column(Text, server_default=text("''"))
    # A parent overlaps its components; the two are never added (migration 0009).
    parent_code: Mapped[str | None] = mapped_column(ForeignKey("indicator.code"))
    display_unit_code: Mapped[str | None] = mapped_column(ForeignKey("unit.code"))


class Area(Base):
    __tablename__ = "area"

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    code: Mapped[str] = mapped_column(Text, unique=True)
    level: Mapped[str] = mapped_column(AREA_LEVEL)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("area.id"))
    name_en: Mapped[str] = mapped_column(Text)
    name_ar: Mapped[str] = mapped_column(Text)
    valid_from: Mapped[date | None]
    valid_to: Mapped[date | None]
    iso_3166_2: Mapped[str | None] = mapped_column(Text)
    code_authority: Mapped[str] = mapped_column(Text, server_default=text("'osrip'"))
    verified_on: Mapped[date | None]
    registry_note_en: Mapped[str | None] = mapped_column(Text)
    registry_note_ar: Mapped[str | None] = mapped_column(Text)
    # False for a published reporting group whose member governorates are not stated.
    members_stated: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class GeoReference(Base):
    """A published document used to establish registry entries (not a data source)."""

    __tablename__ = "geo_reference"

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    code: Mapped[str] = mapped_column(Text, unique=True)
    publisher: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(Text)
    published_on: Mapped[date | None]
    page_updated_on: Mapped[date | None]
    accessed_on: Mapped[date]
    supports: Mapped[str] = mapped_column(Text)


class AreaReference(Base):
    __tablename__ = "area_reference"

    area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("area.id"), primary_key=True)
    geo_reference_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("geo_reference.id"), primary_key=True
    )
    supports: Mapped[list[str]] = mapped_column(ARRAY(Text))


class AreaRegistryVerification(Base):
    """Append-only (database trigger)."""

    __tablename__ = "area_registry_verification"

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    verified_on: Mapped[date]
    expected_governorates: Mapped[int] = mapped_column(Integer)
    expected_wilayats: Mapped[int] = mapped_column(Integer)
    basis_en: Mapped[str] = mapped_column(Text)
    basis_ar: Mapped[str] = mapped_column(Text)
    reference_codes: Mapped[list[str]] = mapped_column(ARRAY(Text))


class Commodity(Base):
    __tablename__ = "commodity"

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name_en: Mapped[str] = mapped_column(Text)
    name_ar: Mapped[str] = mapped_column(Text)
    product_form: Mapped[str] = mapped_column(Text)
    classification_system: Mapped[str | None] = mapped_column(Text)
    classification_version: Mapped[str | None] = mapped_column(Text)
    trade_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    quantity_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unit.id"))
    mapping_status: Mapped[str] = mapped_column(Text, server_default=text("'provisional'"))
    synthetic_only: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class Partner(Base):
    __tablename__ = "partner"

    id: Mapped[uuid.UUID] = mapped_column(**UUID_PK)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name_en: Mapped[str] = mapped_column(Text)
    name_ar: Mapped[str] = mapped_column(Text)
    is_fictional: Mapped[bool] = mapped_column(Boolean)


class AreaGroupMember(Base):
    """Member governorates of a published reporting group (never used to split its values)."""

    __tablename__ = "area_group_member"

    group_area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("area.id"), primary_key=True)
    member_area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("area.id"), primary_key=True)


class UnitConversion(Base):
    """An explicit conversion rule within one physical dimension (migration 0009)."""

    __tablename__ = "unit_conversion"

    from_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unit.id"), primary_key=True)
    to_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unit.id"), primary_key=True)
    factor: Mapped[Decimal] = mapped_column(Numeric)
    basis: Mapped[str] = mapped_column(Text)
