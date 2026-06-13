from typing import Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.modules.users.models import User, UserRole
from app.modules.system_audit_logs.schemas import SystemAuditLogListResponse
from app.modules.system_audit_logs.service import SystemAuditLogService

router = APIRouter()

@router.get("/audit-logs", response_model=SystemAuditLogListResponse)
async def get_system_audit_logs(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: str | None = Query(None, description="Search across actions, actors, roles, or IPs"),
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    service = SystemAuditLogService(db)
    items, total = await service.get_audit_logs(page=page, size=size, search=search)
    return {
        "items": items,
        "total": total
    }
