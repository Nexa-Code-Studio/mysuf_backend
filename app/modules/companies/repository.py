from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.modules.companies.models import Company


class CompanyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_companies(self) -> List[Company]:
        result = await self.db.execute(select(Company).order_by(Company.timestamp.desc()))
        return list(result.scalars().all())

    async def get_company(self, company_id: UUID) -> Optional[Company]:
        result = await self.db.execute(select(Company).filter(Company.id == company_id))
        return result.scalars().first()

    async def create_company(self, company: Company) -> Company:
        """Add a new company to the session (does NOT commit – caller is responsible)."""
        self.db.add(company)
        await self.db.flush()   # flushes so company.id is populated without committing
        return company

    async def update_company(self, company: Company) -> Company:
        self.db.add(company)
        await self.db.commit()
        await self.db.refresh(company)
        return company

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()
