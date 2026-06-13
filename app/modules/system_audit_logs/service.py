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
        # Check if table is empty
        check_stmt = select(func.count(SystemAuditLog.id))
        count_existing = (await self.db.execute(check_stmt)).scalar() or 0

        if count_existing == 0:
            await self.seed_default_logs()

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

    async def seed_default_logs(self) -> None:
        now = datetime.utcnow()
        mock_data = [
            ("Rama Utama", "Super Admin", "Approve perusahaan: PT Logistik Nusantara Maju", "103.24.118.12", now - timedelta(minutes=5)),
            ("Sari Widodo", "Admin Pemerintah", "Update bobot kelayakan: NJKB 40%", "180.252.91.44", now - timedelta(minutes=17)),
            ("Rama Utama", "Super Admin", "Reject warga komersial: KTP 3174012345678901", "103.24.118.12", now - timedelta(hours=10, minutes=30)),
            ("Dewi Kusuma", "Admin Perusahaan", "Reset MFA akun perusahaan", "36.85.101.77", now - timedelta(hours=13, minutes=5)),
            ("Rama Utama", "Super Admin", "Tambah user baru: Admin SPBU Bandung", "103.24.118.12", now - timedelta(hours=13, minutes=45)),
        ]

        for name, role, action, ip, created_at in mock_data:
            log_entry = SystemAuditLog(
                actor_id=None,
                actor_name_snapshot=name,
                actor_role_snapshot=role,
                action=action,
                ip_address=ip,
                created_at=created_at
            )
            self.db.add(log_entry)
        await self.db.commit()
