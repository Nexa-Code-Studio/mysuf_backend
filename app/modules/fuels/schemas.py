from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.modules.fuels.models import FuelCategory, SubsidyType

class FuelTypeResponse(BaseModel):
    id: UUID
    name: str
    octane: str | None = None
    category: FuelCategory
    price_per_liter: float
    subsidy_price_per_liter: float | None = None
    subsidy_type: SubsidyType

    model_config = ConfigDict(from_attributes=True)
