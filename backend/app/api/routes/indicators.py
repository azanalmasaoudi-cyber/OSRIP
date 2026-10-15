from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.domain.enums import PhysicalDimension
from app.models import Indicator, Unit
from app.schemas.indicators import IndicatorOut, UnitOut

router = APIRouter(tags=["indicators"])


@router.get("/indicators", response_model=list[IndicatorOut])
def list_indicators(session: Annotated[Session, Depends(get_session)]) -> list[IndicatorOut]:
    """Booklet Table 3.5: public definitions and compatible units."""
    units_by_dimension: dict[PhysicalDimension, list[UnitOut]] = defaultdict(list)
    for unit in session.scalars(select(Unit).order_by(Unit.code)):
        units_by_dimension[unit.dimension].append(UnitOut.model_validate(unit))

    result: list[IndicatorOut] = []
    for indicator in session.scalars(select(Indicator).order_by(Indicator.section, Indicator.code)):
        out = IndicatorOut.model_validate(indicator)
        out.compatible_units = units_by_dimension[indicator.dimension]
        result.append(out)
    return result
