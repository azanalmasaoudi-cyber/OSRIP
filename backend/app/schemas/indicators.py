import uuid

from pydantic import BaseModel, ConfigDict

from app.domain.enums import PhysicalDimension, Section, ValueType


class UnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    dimension: PhysicalDimension
    label_en: str
    label_ar: str


class IndicatorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    section: Section
    measure: str
    dimension: PhysicalDimension
    value_type: ValueType
    requires_commodity: bool
    requires_flow: bool
    name_en: str
    name_ar: str
    definition_en: str
    definition_ar: str
    compatible_units: list[UnitOut] = []


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
