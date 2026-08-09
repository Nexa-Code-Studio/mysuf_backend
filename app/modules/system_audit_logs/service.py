from datetime import datetime, timedelta
from uuid import UUID
from fastapi import Request
from sqlalchemy import select, func, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.system_audit_logs.models import SystemAuditLog
from app.modules.users.models import User, UserRole

class SystemAuditLogService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def resolve_ip(request: Request) -> str:
        for header in ["x-forwarded-for", "x-real-ip", "X-Forwarded-For", "X-Real-IP"]:
            val = request.headers.get(header)
            if val:
                return val.split(",")[0].strip()
        return request.client.host if request.client else "127.0.0.1"

    def get_clean_role(self, roles: list[UserRole]) -> str:
        if not roles:
            return "Unknown"
        
        role_priority = [
            UserRole.SUPER_ADMIN,
            UserRole.GOV_ADMIN,
            UserRole.COMPANY_ADMIN,
            UserRole.SPBU_ADMIN,
            UserRole.SALES_OFFICER,
            UserRole.BUYER
        ]
        
        primary_role = None
        for r in role_priority:
            if r in roles:
                primary_role = r
                break
        
        if not primary_role:
            primary_role = roles[0]
            
        role_map = {
            UserRole.SUPER_ADMIN: "Super Admin",
            UserRole.GOV_ADMIN: "Admin Pemerintah",
            UserRole.COMPANY_ADMIN: "Admin Perusahaan",
            UserRole.SPBU_ADMIN: "Admin SPBU",
            UserRole.SALES_OFFICER: "Sales Officer",
            UserRole.BUYER: "Warga Komersial"
        }
        return role_map.get(primary_role, str(primary_role))

    async def log_action(
        self,
        actor: User | None,
        action: str,
        ip_address: str
    ) -> SystemAuditLog:
        actor_id = None
        actor_name = "System"
        actor_role = "System"

        if actor:
            actor_id = actor.id
            actor_name = actor.name
            actor_role = self.get_clean_role(actor.role)

        log_entry = SystemAuditLog(
            actor_id=actor_id,
            actor_name_snapshot=actor_name,
            actor_role_snapshot=actor_role,
            action=action,
            ip_address=ip_address,
            created_at=datetime.utcnow()
        )
        self.db.add(log_entry)
        await self.db.commit()
        return log_entry

    async def get_audit_logs(
        self,
        page: int = 1,
        size: int = 100,
        search: str | None = None
    ) -> tuple[list[SystemAuditLog], int]:
        # Build main query
        stmt = select(SystemAuditLog)

        if search:
            # Search across action, actor name snapshot, actor role snapshot, and IP address
            stmt = stmt.filter(
                or_(
                    SystemAuditLog.action.ilike(f"%{search}%"),
                    SystemAuditLog.actor_name_snapshot.ilike(f"%{search}%"),
                    SystemAuditLog.actor_role_snapshot.ilike(f"%{search}%"),
                    SystemAuditLog.ip_address.ilike(f"%{search}%")
                )
            )

        # Get total count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        # Sort by created_at desc
        stmt = stmt.order_by(desc(SystemAuditLog.created_at)).offset((page - 1) * size).limit(size)
        result = await self.db.execute(stmt)
        items = result.scalars().all()

        return list(items), total

