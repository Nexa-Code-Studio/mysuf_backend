from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.modules.wallets.models import OwnerType

class WalletBase(BaseModel):
    owner_type: OwnerType
    owner_id: UUID

class WalletResponse(WalletBase):
    id: UUID
    balance: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime
    nik_masked: str | None = None
    nik: str | None = None

    model_config = ConfigDict(from_attributes=True)
