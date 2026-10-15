import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, ForeignKeyConstraint, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.enums import DataMode, Frequency, QualityStatus, TradeFlow
from app.models.types import DATA_MODE, FREQUENCY, QUALITY_STATUS, TRADE_FLOW


class Observation(Base):
    __tablename__ = "observation"
    __table_args__ = (
        ForeignKeyConstraint(
            ["dataset_version_id", "data_mode"],
            ["dataset_version.id", "dataset_version.data_mode"],
            name="fk_observation_version_mode",
        ),
        # uq_observation_natural_key (NULLS NOT DISTINCT) is defined in the SQL migration.
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    dataset_version_id: Mapped[uuid.UUID]
    data_mode: Mapped[DataMode] = mapped_column(DATA_MODE)
    indicator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("indicator.id"))
    area_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("area.id"))
    period_start: Mapped[date]
    period_end: Mapped[date]
    period_complete: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    frequency: Mapped[Frequency] = mapped_column(FREQUENCY)
    value: Mapped[Decimal | None] = mapped_column(Numeric)  # None = missing, never 0
    unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("unit.id"))
    commodity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("commodity.id"))
    partner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("partner.id"))
    flow: Mapped[TradeFlow | None] = mapped_column(TRADE_FLOW)
    valuation_basis: Mapped[str | None] = mapped_column(Text)
    quality_status: Mapped[QualityStatus] = mapped_column(
        QUALITY_STATUS, server_default=text("'accepted'")
    )
    source_row: Mapped[str] = mapped_column(Text)
    # Reference-pack provenance (migration 0009).
    record_ref: Mapped[str | None] = mapped_column(Text)
    source_locator: Mapped[str | None] = mapped_column(Text)
    revision_status: Mapped[str | None] = mapped_column(Text)
    value_operator: Mapped[str | None] = mapped_column(Text)  # ">" keeps "more than 95"
    statement_date: Mapped[date | None]
    note: Mapped[str | None] = mapped_column(Text)
