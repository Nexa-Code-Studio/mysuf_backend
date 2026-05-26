from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.core.database import AsyncSessionLocal
from app.modules.fuels.models import FuelCategory, FuelType, SubsidyType
from app.modules.gas_stations.models import GasStation
from app.modules.registries.models import KK
from app.modules.subsidies.models import EligibilityStatus, KKSubsidyEligibility, SubsidyOwnerType, SubsidyPolicy, SubsidyQuota
from app.modules.transactions.models import FuelTransaction, FuelTransactionStatus, PaymentMethod, PaymentStatus, PaymentTransaction
from app.modules.transactions.schemas import FuelPurchaseRequest, QrisFuelPurchaseRequest, XenditFuelPurchaseRequest
from app.modules.transactions.service import TransactionService
from app.modules.users.models import BuyerProfile, User, UserRole, VerificationStatus
from app.modules.vehicles.models import (
    VehicleOwnership,
    VehicleOwnerType,
    VehicleOwnershipStatus,
    VehicleQuotaMode,
    VehicleUsageType,
)
from app.modules.wallets.models import OwnerType, Wallet


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *, post_payload: dict, get_payload: dict):
        self._post_payload = post_payload
        self._get_payload = get_payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        return _FakeResponse(201, self._post_payload)

    async def get(self, url, **kwargs):
        return _FakeResponse(200, self._get_payload)


async def _build_qris_fixture(session, usage_type: VehicleUsageType):
    existing_policy = (
        await session.execute(
            select(SubsidyPolicy).where(SubsidyPolicy.usage_type == usage_type),
        )
    ).scalars().first()

    gas_station = GasStation(
        id=uuid4(),
        name=f"SPBU Test {uuid4()}",
        longitude=106.8,
        latitude=-6.2,
    )
    buyer_user = User(
        id=uuid4(),
        name="Buyer QRIS",
        email=f"buyer_{uuid4()}@example.com",
        password="hashed-password",
        role=[UserRole.BUYER],
        is_active=True,
    )
    cashier_user = User(
        id=uuid4(),
        name="Cashier QRIS",
        email=f"cashier_{uuid4()}@example.com",
        password="hashed-password",
        role=[UserRole.SALES_OFFICER],
        is_active=True,
        gas_station_id=gas_station.id,
    )
    kk = KK(id=uuid4(), code=f"KK-{uuid4()}")
    buyer_profile = BuyerProfile(
        id=uuid4(),
        nik_snapshot=f"3201{str(uuid4().int)[:12]}",
        ktp_nfc_id_snapshot=f"nfc-{uuid4()}",
        user_id=buyer_user.id,
        kk_id=kk.id,
        verification_status=VerificationStatus.VERIFIED,
        risk_score=Decimal("0"),
        is_pin_active=False,
    )
    fuel = FuelType(
        id=uuid4(),
        name=f"Pertalite-{uuid4()}",
        category=FuelCategory.GASOLINE,
        price_per_liter=Decimal("10000.00"),
        subsidy_price_per_liter=Decimal("6500.00"),
        subsidy_type=SubsidyType.SUBSIDIZED,
    )
    policy = existing_policy or SubsidyPolicy(
        id=uuid4(),
        name=f"Policy-{usage_type.value}-{uuid4()}",
        usage_type=usage_type,
        monthly_quota_liters=Decimal("60.00"),
        max_allowed_njkb=Decimal("500000000.00"),
        is_active=True,
    )
    vehicle = VehicleOwnership(
        id=uuid4(),
        owner_type=VehicleOwnerType.BUYER_PROFILE,
        owner_id=buyer_profile.id,
        vehicle_id=uuid4(),
        ownership_status=VehicleOwnershipStatus.PERSONAL,
        usage_type=usage_type,
        quota_mode=VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA,
        plate_number_snapshot=f"B {str(uuid4().int)[:4]} QR",
        ktp_nfc_id_snapshot=buyer_profile.ktp_nfc_id_snapshot,
    )

    session.add_all([gas_station, buyer_user, cashier_user, kk, buyer_profile, fuel, vehicle])
    if existing_policy is None:
        session.add(policy)
    await session.commit()

    return {
        "cashier": cashier_user,
        "buyer_user": buyer_user,
        "buyer_profile": buyer_profile,
        "fuel": fuel,
        "vehicle": vehicle,
        "gas_station": gas_station,
        "ids": {
            "gas_station": gas_station.id,
            "buyer_user": buyer_user.id,
            "cashier_user": cashier_user.id,
            "buyer_profile": buyer_profile.id,
            "kk": kk.id,
            "fuel": fuel.id,
            "policy": policy.id,
            "vehicle": vehicle.id,
            "vehicle_owner_ref": vehicle.vehicle_id,
        },
    }


async def _build_wallet_purchase_fixture(
    session,
    *,
    eligibility_status: EligibilityStatus,
    quota_liters: Decimal | None = None,
    used_liters: Decimal = Decimal("0.00"),
):
    existing_policy = (
        await session.execute(
            select(SubsidyPolicy).where(SubsidyPolicy.usage_type == VehicleUsageType.PERSONAL),
        )
    ).scalars().first()

    gas_station = GasStation(
        id=uuid4(),
        name=f"SPBU Personal {uuid4()}",
        longitude=106.8,
        latitude=-6.2,
    )
    buyer_user = User(
        id=uuid4(),
        name="Buyer Wallet",
        email=f"buyer_wallet_{uuid4()}@example.com",
        password="hashed-password",
        role=[UserRole.BUYER],
        is_active=True,
    )
    cashier_user = User(
        id=uuid4(),
        name="Cashier Wallet",
        email=f"cashier_wallet_{uuid4()}@example.com",
        password="hashed-password",
        role=[UserRole.SALES_OFFICER],
        is_active=True,
        gas_station_id=gas_station.id,
    )
    kk = KK(id=uuid4(), code=f"KK-{uuid4()}")
    buyer_profile = BuyerProfile(
        id=uuid4(),
        nik_snapshot=f"3201{str(uuid4().int)[:12]}",
        ktp_nfc_id_snapshot=f"nfc-{uuid4()}",
        user_id=buyer_user.id,
        kk_id=kk.id,
        verification_status=VerificationStatus.VERIFIED,
        risk_score=Decimal("0"),
        is_pin_active=False,
    )
    wallet = Wallet(
        id=uuid4(),
        owner_type=OwnerType.USER,
        owner_id=buyer_user.id,
        balance=Decimal("1000000.00"),
        is_active=True,
    )
    fuel = FuelType(
        id=uuid4(),
        name=f"Pertalite-Personal-{uuid4()}",
        category=FuelCategory.GASOLINE,
        price_per_liter=Decimal("10000.00"),
        subsidy_price_per_liter=Decimal("6500.00"),
        subsidy_type=SubsidyType.SUBSIDIZED,
    )
    policy = existing_policy or SubsidyPolicy(
        id=uuid4(),
        name=f"Policy-PERSONAL-{uuid4()}",
        usage_type=VehicleUsageType.PERSONAL,
        monthly_quota_liters=Decimal("60.00"),
        max_allowed_njkb=Decimal("500000000.00"),
        is_active=True,
    )
    vehicle = VehicleOwnership(
        id=uuid4(),
        owner_type=VehicleOwnerType.BUYER_PROFILE,
        owner_id=buyer_profile.id,
        vehicle_id=uuid4(),
        ownership_status=VehicleOwnershipStatus.PERSONAL,
        usage_type=VehicleUsageType.PERSONAL,
        quota_mode=VehicleQuotaMode.OWNER_PERSONAL_QUOTA,
        plate_number_snapshot=f"B {str(uuid4().int)[:4]} WL",
        ktp_nfc_id_snapshot=buyer_profile.ktp_nfc_id_snapshot,
    )

    eligibility = KKSubsidyEligibility(
        id=uuid4(),
        kk_id=kk.id,
        subsidy_policy_id=policy.id,
        total_njkb=Decimal("450000000.00"),
        eligibility_status=eligibility_status,
        eligibility_reason="test fixture",
        checked_at=datetime.utcnow(),
    )

    session.add_all([gas_station, buyer_user, cashier_user, kk, buyer_profile, wallet, fuel, vehicle, eligibility])
    if existing_policy is None:
        session.add(policy)

    quota = None
    if quota_liters is not None:
        quota = SubsidyQuota(
            id=uuid4(),
            owner_type=SubsidyOwnerType.BUYER_PROFILE,
            owner_id=buyer_profile.id,
            subsidy_policy_id=policy.id,
            kk_subsidy_eligibility_id=eligibility.id,
            month=datetime.utcnow().month,
            year=datetime.utcnow().year,
            quota_liters=quota_liters,
            used_liters=used_liters,
            is_active=True,
        )
        session.add(quota)

    await session.commit()

    return {
        "cashier": cashier_user,
        "buyer_user": buyer_user,
        "buyer_profile": buyer_profile,
        "fuel": fuel,
        "vehicle": vehicle,
        "gas_station": gas_station,
        "wallet": wallet,
        "eligibility": eligibility,
        "quota": quota,
        "ids": {
            "gas_station": gas_station.id,
            "buyer_user": buyer_user.id,
            "cashier_user": cashier_user.id,
            "buyer_profile": buyer_profile.id,
            "kk": kk.id,
            "fuel": fuel.id,
            "policy": policy.id if existing_policy is None else None,
            "vehicle": vehicle.id,
            "wallet": wallet.id,
            "eligibility": eligibility.id,
            "subsidy_quota": quota.id if quota is not None else None,
        },
    }


async def _cleanup_fixture(session, ids: dict):
    from app.modules.subsidies.models import SubsidyQuota
    from app.modules.subsidies.models import SubsidyOwnerType
    from app.modules.wallets.models import Wallet

    fuel_transactions = (
        await session.execute(
            select(FuelTransaction.id).where(
                FuelTransaction.verified_by_user_id == ids["cashier_user"],
            ),
        )
    ).scalars().all()
    if fuel_transactions:
        await session.execute(
            delete(PaymentTransaction).where(
                PaymentTransaction.fuel_transaction_id.in_(fuel_transactions),
            ),
        )
    await session.execute(delete(FuelTransaction).where(FuelTransaction.verified_by_user_id == ids["cashier_user"]))

    if ids.get("subsidy_quota"):
        await session.execute(delete(SubsidyQuota).where(SubsidyQuota.id == ids["subsidy_quota"]))
    vehicle_owner_ref = ids.get("vehicle_owner_ref")
    if vehicle_owner_ref:
        await session.execute(
            delete(SubsidyQuota).where(
                SubsidyQuota.owner_type == SubsidyOwnerType.VEHICLE,
                SubsidyQuota.owner_id == vehicle_owner_ref,
            ),
        )
    if ids.get("eligibility"):
        await session.execute(delete(KKSubsidyEligibility).where(KKSubsidyEligibility.id == ids["eligibility"]))
    if ids.get("policy"):
        await session.execute(delete(SubsidyPolicy).where(SubsidyPolicy.id == ids["policy"]))
    await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id == ids["vehicle"]))
    await session.execute(delete(FuelType).where(FuelType.id == ids["fuel"]))
    await session.execute(delete(BuyerProfile).where(BuyerProfile.id == ids["buyer_profile"]))
    await session.execute(delete(Wallet).where(Wallet.owner_id == ids["buyer_user"]))
    await session.execute(delete(User).where(User.id.in_([ids["buyer_user"], ids["cashier_user"]])))
    await session.execute(delete(KK).where(KK.id == ids["kk"]))
    await session.execute(delete(GasStation).where(GasStation.id == ids["gas_station"]))
    await session.commit()


@pytest.mark.anyio
async def test_qris_fuel_purchase_success_keeps_reserved_quota(monkeypatch):
    expires_at = (datetime.utcnow() + timedelta(minutes=30)).isoformat() + "Z"
    monkeypatch.setattr(
        "app.modules.transactions.service.httpx.AsyncClient",
        lambda *args, **kwargs: _FakeAsyncClient(
            post_payload={
                "payment_request_id": "pr-qris-success",
                "status": "REQUIRES_ACTION",
                "actions": [
                    {
                        "type": "PRESENT_TO_CUSTOMER",
                        "descriptor": "QR_STRING",
                        "value": "000201SUCCESSQR",
                    }
                ],
                "channel_properties": {"expires_at": expires_at},
            },
            get_payload={
                "payment_request_id": "pr-qris-success",
                "status": "SUCCEEDED",
                "channel_properties": {"expires_at": expires_at},
            },
        ),
    )

    async with AsyncSessionLocal() as session:
        fixture = await _build_qris_fixture(session, VehicleUsageType.COMMERCIAL_MOTORCYCLE)
        service = TransactionService(session)
        request = QrisFuelPurchaseRequest(
            nik=fixture["buyer_profile"].nik_snapshot,
            plate_number=fixture["vehicle"].plate_number_snapshot,
            fuel_type_id=fixture["fuel"].id,
            liters=Decimal("10.00"),
            total_amount=Decimal("65000.00"),
        )

        try:
            created = await service.create_qris_fuel_purchase(fixture["cashier"], request)
            assert created["status"] == "PENDING"
            assert created["qr_string"] == "000201SUCCESSQR"

            fuel_tx = await service.repo.get_fuel_transaction_by_id(created["transaction_id"])
            assert fuel_tx is not None
            quota = fuel_tx.subsidy_quota
            assert quota is not None
            await session.refresh(quota)
            assert Decimal(quota.used_liters) == Decimal("10.00")

            status_payload = await service.get_qris_fuel_purchase_status(
                fixture["cashier"],
                fuel_tx.id,
            )
            assert status_payload["status"] == "PAID"

            await session.refresh(fuel_tx)
            await session.refresh(quota)
            payment_tx = await service.repo.get_payment_transaction_by_fuel_transaction_id(fuel_tx.id)
            assert fuel_tx.transaction_status == FuelTransactionStatus.COMPLETED
            assert payment_tx is not None
            assert payment_tx.status == PaymentStatus.PAID
            assert Decimal(quota.used_liters) == Decimal("10.00")
        finally:
            await _cleanup_fixture(session, fixture["ids"])


@pytest.mark.anyio
async def test_qris_fuel_purchase_expired_releases_reserved_quota(monkeypatch):
    expires_at = (datetime.utcnow() + timedelta(minutes=30)).isoformat() + "Z"
    monkeypatch.setattr(
        "app.modules.transactions.service.httpx.AsyncClient",
        lambda *args, **kwargs: _FakeAsyncClient(
            post_payload={
                "payment_request_id": "pr-qris-expired",
                "status": "REQUIRES_ACTION",
                "actions": [
                    {
                        "type": "PRESENT_TO_CUSTOMER",
                        "descriptor": "QR_STRING",
                        "value": "000201EXPIREDQR",
                    }
                ],
                "channel_properties": {"expires_at": expires_at},
            },
            get_payload={
                "payment_request_id": "pr-qris-expired",
                "status": "EXPIRED",
                "channel_properties": {"expires_at": expires_at},
            },
        ),
    )

    async with AsyncSessionLocal() as session:
        fixture = await _build_qris_fixture(session, VehicleUsageType.COMMERCIAL_CAR)
        service = TransactionService(session)
        request = QrisFuelPurchaseRequest(
            nik=fixture["buyer_profile"].nik_snapshot,
            plate_number=fixture["vehicle"].plate_number_snapshot,
            fuel_type_id=fixture["fuel"].id,
            liters=Decimal("8.00"),
            total_amount=Decimal("52000.00"),
        )

        try:
            created = await service.create_qris_fuel_purchase(fixture["cashier"], request)
            fuel_tx = await service.repo.get_fuel_transaction_by_id(created["transaction_id"])
            assert fuel_tx is not None
            quota = fuel_tx.subsidy_quota
            assert quota is not None
            await session.refresh(quota)
            assert Decimal(quota.used_liters) == Decimal("8.00")

            status_payload = await service.get_qris_fuel_purchase_status(
                fixture["cashier"],
                fuel_tx.id,
            )
            assert status_payload["status"] == "EXPIRED"

            await session.refresh(fuel_tx)
            await session.refresh(quota)
            payment_tx = await service.repo.get_payment_transaction_by_fuel_transaction_id(fuel_tx.id)
            assert fuel_tx.transaction_status == FuelTransactionStatus.CANCELLED
            assert payment_tx is not None
            assert payment_tx.status == PaymentStatus.EXPIRED
            assert Decimal(quota.used_liters) == Decimal("0")
        finally:
            await _cleanup_fixture(session, fixture["ids"])


@pytest.mark.anyio
async def test_xendit_fuel_purchase_success_keeps_reserved_quota(monkeypatch):
    expires_at = (datetime.utcnow() + timedelta(minutes=30)).isoformat() + "Z"
    monkeypatch.setattr(
        "app.modules.transactions.service.httpx.AsyncClient",
        lambda *args, **kwargs: _FakeAsyncClient(
            post_payload={
                "payment_session_id": "ps-xendit-success",
                "id": "ps-xendit-success",
                "payment_link_url": "https://checkout.xendit.co/pay/ps-xendit-success",
                "status": "PENDING",
                "expires_at": expires_at,
            },
            get_payload={
                "payment_session_id": "ps-xendit-success",
                "status": "COMPLETED",
                "expires_at": expires_at,
            },
        ),
    )

    async with AsyncSessionLocal() as session:
        fixture = await _build_qris_fixture(session, VehicleUsageType.COMMERCIAL_MOTORCYCLE)
        service = TransactionService(session)
        request = XenditFuelPurchaseRequest(
            nik=fixture["buyer_profile"].nik_snapshot,
            plate_number=fixture["vehicle"].plate_number_snapshot,
            fuel_type_id=fixture["fuel"].id,
            liters=Decimal("10.00"),
            total_amount=Decimal("65000.00"),
        )

        try:
            created = await service.create_xendit_fuel_purchase(fixture["cashier"], request)
            assert created["status"] == "PENDING"
            assert created["payment_link_url"] == "https://checkout.xendit.co/pay/ps-xendit-success"

            fuel_tx = await service.repo.get_fuel_transaction_by_id(created["transaction_id"])
            assert fuel_tx is not None
            quota = fuel_tx.subsidy_quota
            assert quota is not None
            await session.refresh(quota)
            assert Decimal(quota.used_liters) == Decimal("10.00")

            status_payload = await service.get_xendit_fuel_purchase_status(
                fixture["cashier"],
                fuel_tx.id,
            )
            assert status_payload["status"] == "PAID"

            await session.refresh(fuel_tx)
            await session.refresh(quota)
            payment_tx = await service.repo.get_payment_transaction_by_fuel_transaction_id(fuel_tx.id)
            assert fuel_tx.transaction_status == FuelTransactionStatus.COMPLETED
            assert payment_tx is not None
            assert payment_tx.status == PaymentStatus.PAID
            assert Decimal(quota.used_liters) == Decimal("10.00")
        finally:
            await _cleanup_fixture(session, fixture["ids"])


@pytest.mark.anyio
async def test_xendit_fuel_purchase_expired_releases_reserved_quota(monkeypatch):
    expires_at = (datetime.utcnow() + timedelta(minutes=30)).isoformat() + "Z"
    monkeypatch.setattr(
        "app.modules.transactions.service.httpx.AsyncClient",
        lambda *args, **kwargs: _FakeAsyncClient(
            post_payload={
                "payment_session_id": "ps-xendit-expired",
                "id": "ps-xendit-expired",
                "payment_link_url": "https://checkout.xendit.co/pay/ps-xendit-expired",
                "status": "PENDING",
                "expires_at": expires_at,
            },
            get_payload={
                "payment_session_id": "ps-xendit-expired",
                "status": "EXPIRED",
                "expires_at": expires_at,
            },
        ),
    )

    async with AsyncSessionLocal() as session:
        fixture = await _build_qris_fixture(session, VehicleUsageType.COMMERCIAL_CAR)
        service = TransactionService(session)
        request = XenditFuelPurchaseRequest(
            nik=fixture["buyer_profile"].nik_snapshot,
            plate_number=fixture["vehicle"].plate_number_snapshot,
            fuel_type_id=fixture["fuel"].id,
            liters=Decimal("8.00"),
            total_amount=Decimal("52000.00"),
        )

        try:
            created = await service.create_xendit_fuel_purchase(fixture["cashier"], request)
            fuel_tx = await service.repo.get_fuel_transaction_by_id(created["transaction_id"])
            assert fuel_tx is not None
            quota = fuel_tx.subsidy_quota
            assert quota is not None
            await session.refresh(quota)
            assert Decimal(quota.used_liters) == Decimal("8.00")

            status_payload = await service.get_xendit_fuel_purchase_status(
                fixture["cashier"],
                fuel_tx.id,
            )
            assert status_payload["status"] == "EXPIRED"

            await session.refresh(fuel_tx)
            await session.refresh(quota)
            payment_tx = await service.repo.get_payment_transaction_by_fuel_transaction_id(fuel_tx.id)
            assert fuel_tx.transaction_status == FuelTransactionStatus.CANCELLED
            assert payment_tx is not None
            assert payment_tx.status == PaymentStatus.EXPIRED
            assert Decimal(quota.used_liters) == Decimal("0")
        finally:
            await _cleanup_fixture(session, fixture["ids"])


@pytest.mark.anyio
async def test_wallet_fuel_purchase_ineligible_uses_market_price():
    async with AsyncSessionLocal() as session:
        fixture = await _build_wallet_purchase_fixture(
            session,
            eligibility_status=EligibilityStatus.NOT_ELIGIBLE,
        )
        service = TransactionService(session)
        request = FuelPurchaseRequest(
            nik=fixture["buyer_profile"].nik_snapshot,
            plate_number=fixture["vehicle"].plate_number_snapshot,
            fuel_type_id=fixture["fuel"].id,
            liters=Decimal("10.00"),
            total_amount=Decimal("100000.00"),
            payment_method=PaymentMethod.WALLET,
        )

        try:
            created = await service.execute_fuel_purchase(fixture["cashier"], request)
            assert created["status"] == "COMPLETED"
            assert Decimal(created["total_amount"]) == Decimal("100000.00")

            fuel_tx = await service.repo.get_fuel_transaction_by_id(created["transaction_id"])
            assert fuel_tx is not None
            assert fuel_tx.is_subsidized is False
            assert Decimal(fuel_tx.subsidized_liters) == Decimal("0")
            assert Decimal(fuel_tx.non_subsidized_liters) == Decimal("10.00")
            assert Decimal(fuel_tx.total_amount) == Decimal("100000.00")
            assert fuel_tx.subsidy_quota_id is None
            assert fuel_tx.kk_subsidy_eligibility_id is None

            await session.refresh(fixture["wallet"])
            assert Decimal(fixture["wallet"].balance) == Decimal("900000.00")
        finally:
            await _cleanup_fixture(session, fixture["ids"])


@pytest.mark.anyio
async def test_wallet_fuel_purchase_partial_subsidy_splits_liters():
    async with AsyncSessionLocal() as session:
        fixture = await _build_wallet_purchase_fixture(
            session,
            eligibility_status=EligibilityStatus.ELIGIBLE,
            quota_liters=Decimal("20.00"),
            used_liters=Decimal("0.00"),
        )
        service = TransactionService(session)
        request = FuelPurchaseRequest(
            nik=fixture["buyer_profile"].nik_snapshot,
            plate_number=fixture["vehicle"].plate_number_snapshot,
            fuel_type_id=fixture["fuel"].id,
            liters=Decimal("50.00"),
            total_amount=Decimal("430000.00"),
            payment_method=PaymentMethod.WALLET,
        )

        try:
            created = await service.execute_fuel_purchase(fixture["cashier"], request)
            assert created["status"] == "COMPLETED"
            assert Decimal(created["total_amount"]) == Decimal("430000.00")

            fuel_tx = await service.repo.get_fuel_transaction_by_id(created["transaction_id"])
            assert fuel_tx is not None
            assert fuel_tx.is_subsidized is True
            assert Decimal(fuel_tx.subsidized_liters) == Decimal("20.00")
            assert Decimal(fuel_tx.non_subsidized_liters) == Decimal("30.00")
            assert Decimal(fuel_tx.total_amount) == Decimal("430000.00")
            assert fuel_tx.subsidy_quota_id is not None
            assert fuel_tx.kk_subsidy_eligibility_id is not None

            quota = fuel_tx.subsidy_quota
            assert quota is not None
            await session.refresh(quota)
            assert Decimal(quota.used_liters) == Decimal("20.00")

            await session.refresh(fixture["wallet"])
            assert Decimal(fixture["wallet"].balance) == Decimal("570000.00")
        finally:
            await _cleanup_fixture(session, fixture["ids"])


@pytest.mark.anyio
async def test_wallet_fuel_purchase_when_quota_exhausted_uses_market_price():
    async with AsyncSessionLocal() as session:
        fixture = await _build_wallet_purchase_fixture(
            session,
            eligibility_status=EligibilityStatus.ELIGIBLE,
            quota_liters=Decimal("20.00"),
            used_liters=Decimal("20.00"),
        )
        service = TransactionService(session)
        request = FuelPurchaseRequest(
            nik=fixture["buyer_profile"].nik_snapshot,
            plate_number=fixture["vehicle"].plate_number_snapshot,
            fuel_type_id=fixture["fuel"].id,
            liters=Decimal("10.00"),
            total_amount=Decimal("65000.00"),
            payment_method=PaymentMethod.WALLET,
        )

        try:
            created = await service.execute_fuel_purchase(fixture["cashier"], request)
            assert created["status"] == "COMPLETED"
            assert Decimal(created["total_amount"]) == Decimal("100000.00")

            fuel_tx = await service.repo.get_fuel_transaction_by_id(created["transaction_id"])
            assert fuel_tx is not None
            assert fuel_tx.is_subsidized is False
            assert Decimal(fuel_tx.subsidized_liters) == Decimal("0")
            assert Decimal(fuel_tx.non_subsidized_liters) == Decimal("10.00")
            assert Decimal(fuel_tx.total_amount) == Decimal("100000.00")
            assert fuel_tx.subsidy_quota_id is None
            assert fuel_tx.kk_subsidy_eligibility_id is None

            quota = fixture["quota"]
            assert quota is not None
            await session.refresh(quota)
            assert Decimal(quota.used_liters) == Decimal("20.00")

            await session.refresh(fixture["wallet"])
            assert Decimal(fixture["wallet"].balance) == Decimal("900000.00")
        finally:
            await _cleanup_fixture(session, fixture["ids"])


@pytest.mark.anyio
async def test_cash_fuel_purchase_rejects_when_paid_amount_is_below_server_total():
    async with AsyncSessionLocal() as session:
        fixture = await _build_wallet_purchase_fixture(
            session,
            eligibility_status=EligibilityStatus.ELIGIBLE,
            quota_liters=Decimal("20.00"),
            used_liters=Decimal("0.00"),
        )
        service = TransactionService(session)
        request = FuelPurchaseRequest(
            nik=fixture["buyer_profile"].nik_snapshot,
            plate_number=fixture["vehicle"].plate_number_snapshot,
            fuel_type_id=fixture["fuel"].id,
            liters=Decimal("50.00"),
            total_amount=Decimal("200000.00"),
            payment_method=PaymentMethod.CASH,
            amount_paid=Decimal("200000.00"),
        )

        try:
            with pytest.raises(HTTPException) as exc_info:
                await service.execute_fuel_purchase(fixture["cashier"], request)

            assert exc_info.value.status_code == 400
            assert exc_info.value.detail == "Nominal uang diterima tidak boleh kurang dari total harga."

            await session.refresh(fixture["wallet"])
            assert Decimal(fixture["wallet"].balance) == Decimal("1000000.00")
        finally:
            await _cleanup_fixture(session, fixture["ids"])
