"""PostgreSQL enum column types bound to the Python enums (types are created by SQL migrations)."""

from enum import StrEnum

from sqlalchemy.dialects.postgresql import ENUM

from app.domain.enums import (
    AccountStatus,
    DataMode,
    DatasetVersionStatus,
    Frequency,
    PhysicalDimension,
    QualityStatus,
    Section,
    TradeFlow,
    ValueType,
)


def pg_enum(enum_cls: type[StrEnum], name: str) -> ENUM:
    return ENUM(
        enum_cls,
        name=name,
        create_type=False,
        values_callable=lambda members: [m.value for m in members],
    )


DATA_MODE = pg_enum(DataMode, "data_mode")
PHYSICAL_DIMENSION = pg_enum(PhysicalDimension, "physical_dimension")
VALUE_TYPE = pg_enum(ValueType, "value_type")
SECTION = pg_enum(Section, "section_code")
TRADE_FLOW = pg_enum(TradeFlow, "trade_flow")
QUALITY_STATUS = pg_enum(QualityStatus, "quality_status")
DATASET_VERSION_STATUS = pg_enum(DatasetVersionStatus, "dataset_version_status")
FREQUENCY = pg_enum(Frequency, "observation_frequency")
ACCOUNT_STATUS = pg_enum(AccountStatus, "account_status")
AREA_LEVEL = ENUM(
    "national",
    "governorate",
    "wilayat",
    "service_area",
    "reporting_group",
    name="area_level",
    create_type=False,
)
ANALYSIS_KIND = ENUM("rule", "forecast", name="analysis_kind", create_type=False)
ANALYSIS_STATUS = ENUM("succeeded", "withheld", "failed", name="analysis_status", create_type=False)
REVIEW_STATUS = ENUM(
    "under_review", "explained", "dismissed", name="review_status", create_type=False
)
REPORT_VISIBILITY = ENUM("private", "published", name="report_visibility", create_type=False)
