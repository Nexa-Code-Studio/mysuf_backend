from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.modules.buyer_registrations.models import (
    BuyerDocumentType,
    BuyerProfileDocument,
    BuyerRegistrationAttempt,
    BuyerRegistrationDocument,
    BuyerRegistrationStatus,
)
from app.modules.registries.models import CitizenRegistryMockup
from app.modules.users.models import BuyerProfile, User


ACTIVE_REGISTRATION_STATUSES = (
    BuyerRegistrationStatus.PENDING,
    BuyerRegistrationStatus.PROCESSING,
    BuyerRegistrationStatus.REVIEW_REQUIRED,
    BuyerRegistrationStatus.VERIFIED,
)


class BuyerRegistrationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).filter(User.email == email))
        return result.scalars().first()

    async def get_active_attempt_by_email(self, email: str) -> BuyerRegistrationAttempt | None:
        result = await self.db.execute(
            select(BuyerRegistrationAttempt)
            .options(selectinload(BuyerRegistrationAttempt.documents))
            .filter(
                BuyerRegistrationAttempt.email == email,
                BuyerRegistrationAttempt.status.in_(ACTIVE_REGISTRATION_STATUSES),
            )
        )
        return result.scalars().first()

    async def get_active_attempt_by_nik(self, nik_input: str) -> BuyerRegistrationAttempt | None:
        result = await self.db.execute(
            select(BuyerRegistrationAttempt)
            .options(selectinload(BuyerRegistrationAttempt.documents))
            .filter(
                BuyerRegistrationAttempt.nik_input == nik_input,
                BuyerRegistrationAttempt.status.in_(ACTIVE_REGISTRATION_STATUSES),
            )
        )
        return result.scalars().first()

    async def create_attempt(self, attempt: BuyerRegistrationAttempt) -> BuyerRegistrationAttempt:
        self.db.add(attempt)
        await self.db.flush()
        return attempt

    async def add_documents(self, documents: list[BuyerRegistrationDocument]) -> None:
        self.db.add_all(documents)

    async def commit(self) -> None:
        await self.db.commit()

    async def rollback(self) -> None:
        await self.db.rollback()

    async def get_attempt_by_id(self, attempt_id: str) -> BuyerRegistrationAttempt | None:
        result = await self.db.execute(
            select(BuyerRegistrationAttempt)
            .options(selectinload(BuyerRegistrationAttempt.documents))
            .filter(BuyerRegistrationAttempt.id == attempt_id)
        )
        return result.scalars().first()

    async def get_citizen_by_nik(self, nik: str) -> CitizenRegistryMockup | None:
        result = await self.db.execute(
            select(CitizenRegistryMockup).filter(CitizenRegistryMockup.nik == nik)
        )
        return result.scalars().first()

    async def flush(self) -> None:
        await self.db.flush()

    async def create_user(self, user: User) -> User:
        self.db.add(user)
        await self.db.flush()
        return user

    async def create_buyer_profile(self, buyer_profile: BuyerProfile) -> BuyerProfile:
        self.db.add(buyer_profile)
        await self.db.flush()
        return buyer_profile

    async def create_buyer_profile_documents(self, documents: list[BuyerProfileDocument]) -> None:
        self.db.add_all(documents)

    def get_document_by_type(
        self,
        attempt: BuyerRegistrationAttempt,
        document_type: BuyerDocumentType,
    ) -> BuyerRegistrationDocument | None:
        return next(
            (document for document in attempt.documents if document.document_type == document_type),
            None,
        )
