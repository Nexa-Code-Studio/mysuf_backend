from datetime import datetime, timedelta
from uuid import UUID
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.spbu_activities.models import SpbuActivityLog, SpbuActivityCategory

class SpbuActivityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_activity(
        self,
        gas_station_id: UUID,
        category: SpbuActivityCategory,
        detail: str,
        user_id: UUID | None = None
    ) -> SpbuActivityLog:
        log_entry = SpbuActivityLog(
            gas_station_id=gas_station_id,
            user_id=user_id,
            category=category,
            detail=detail
        )
        self.db.add(log_entry)
        await self.db.commit()
        return log_entry

    async def get_activity_logs(
        self,
        gas_station_id: UUID,
        category: str | None = None,
        search: str | None = None,
        page: int = 1,
        size: int = 100
    ) -> tuple[list[SpbuActivityLog], int]:
        # Build main query
        stmt = select(SpbuActivityLog).filter(SpbuActivityLog.gas_station_id == gas_station_id)
        if category and category != "Semua":
            # Map category from Indonesian (UI) to Enum if needed
            cat_map = {
                "Sistem": SpbuActivityCategory.Sistem,
                "Penjualan": SpbuActivityCategory.Penjualan,
                "Keamanan": SpbuActivityCategory.Keamanan
            }
            mapped_cat = cat_map.get(category, category)
            stmt = stmt.filter(SpbuActivityLog.category == mapped_cat)

        if search:
            stmt = stmt.filter(SpbuActivityLog.detail.ilike(f"%{search}%"))

        # Get total count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        # Sort by created_at desc
        stmt = stmt.order_by(desc(SpbuActivityLog.created_at)).offset((page - 1) * size).limit(size)
        result = await self.db.execute(stmt)
        items = result.scalars().all()

        return list(items), total

