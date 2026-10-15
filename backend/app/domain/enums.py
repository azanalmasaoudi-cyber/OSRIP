"""Controlled vocabularies shared by the database, API and calculations.

Values are stable machine codes. Human-readable English/Arabic labels live in
the frontend locale files, never here.
"""

from enum import StrEnum


class DataMode(StrEnum):
    """Booklet 3.4: two explicitly separate modes. Never mixed in one query."""

    VERIFIED_SOURCE = "verified_source"
    SYNTHETIC = "synthetic"


class Domain(StrEnum):
    """The three primary domains; electricity and water are sections of one."""

    ENERGY_ESSENTIAL_SERVICES = "energy_essential_services"
    FOOD_SECURITY = "food_security"
    TRADE = "trade"


class Section(StrEnum):
    ELECTRICITY = "electricity"
    WATER = "water"
    FOOD_SECURITY = "food_security"
    TRADE = "trade"


class PhysicalDimension(StrEnum):
    """Unit conversion is permitted only within one dimension (booklet 3.5)."""

    ENERGY = "energy"  # e.g. GWh
    POWER = "power"  # e.g. MW
    VOLUME = "volume"  # e.g. million m3
    MASS = "mass"  # e.g. tonne
    CURRENCY = "currency"  # e.g. OMR (nominal)
    COUNT = "count"  # e.g. subscribers
    RATIO = "ratio"  # e.g. percent
    AREA = "area"  # e.g. feddan


class ValueType(StrEnum):
    """How an observation relates to its period; governs aggregation (3.3)."""

    PERIOD_TOTAL = "period_total"  # flow; summable over non-overlapping periods
    AVERAGE = "average"
    MAXIMUM = "maximum"  # e.g. peak load; never summed
    END_OF_PERIOD = "end_of_period"  # e.g. installed capacity, subscribers
    CUMULATIVE_TO_DATE = "cumulative_to_date"  # never added across months


class TradeFlow(StrEnum):
    IMPORT = "import"
    DOMESTIC_EXPORT = "domestic_export"
    RE_EXPORT = "re_export"


class QualityStatus(StrEnum):
    ACCEPTED = "accepted"
    WARNING = "warning"
    WITHHELD = "withheld"


class DatasetVersionStatus(StrEnum):
    """Also the import lifecycle: draft (uploaded) -> validated -> approved -> published."""

    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class Frequency(StrEnum):
    """Observation frequency; periods must match it (migration 0003 CHECK)."""

    ANNUAL = "annual"
    QUARTERLY = "quarterly"
    MONTHLY = "monthly"
    # A dated statement whose reference period is not stated (migration 0009). Never
    # part of a time series: kept out of trend charts, comparisons and forecasts.
    STATEMENT = "statement"


# Frequencies that describe a regular period and can form a time series.
PERIODIC_FREQUENCIES = (Frequency.ANNUAL, Frequency.QUARTERLY, Frequency.MONTHLY)


class RevisionStatus(StrEnum):
    """How final a published value is, as stated by its source (migration 0009)."""

    REPORTED = "reported"
    PROVISIONAL = "provisional"
    PRELIMINARY = "preliminary"
    ESTIMATE = "estimate"
    OFFICIAL_STATEMENT = "official_statement"
    REPORTED_STATEMENT = "reported_statement"
    REVISED = "revised"


class LocatorKind(StrEnum):
    """What a source URL points at. A catalogue page cannot verify an observation."""

    DIRECT_FILE = "direct_file"
    STATISTICAL_TABLE = "statistical_table"
    CATALOGUE_PAGE = "catalogue_page"
    WEB_PAGE = "web_page"  # an official statement or news report stating the values in its text


class AccountStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class RowOutcome(StrEnum):
    VALID = "valid"
    WARNING = "warning"  # published, with a recorded warning
    REJECTED = "rejected"  # kept in the error report, never published


class Permission(StrEnum):
    """Server-side permission codes (migration 0003 seeds the same codes)."""

    SOURCE_REGISTER = "source.register"
    IMPORT_CREATE = "import.create"
    IMPORT_READ = "import.read"
    IMPORT_VALIDATE = "import.validate"
    IMPORT_MANAGE_ANY = "import.manage_any"
    IMPORT_APPROVE = "import.approve"
    IMPORT_PUBLISH = "import.publish"
    IMPORT_REJECT = "import.reject"
    ANALYSIS_RUN = "analysis.run"
    ASSISTANT_USE = "assistant.use"
    RESEARCH_REVIEW = "research.review"
    REPORT_CREATE = "report.create"
    RECOMMENDATION_REVIEW = "recommendation.review"
    USER_MANAGE = "user.manage"
    AUDIT_READ = "audit.read"


class Role(StrEnum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    DATA_MANAGER = "data_manager"
    ADMINISTRATOR = "administrator"
