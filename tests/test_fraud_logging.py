import pytest
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select, delete

from app.core.database import AsyncSessionLocal
from app.modules.registries.models import KK, VehicleRegistryMockup
from app.modules.users.models import BuyerProfile, User, UserRole, VerificationStatus
from app.modules.vehicles.models import VehicleOwnership, VehicleOwnerType, VehicleOwnershipStatus, VehicleQuotaMode, VehicleUsageType
from app.modules.fuels.models import FuelType, SubsidyType, FuelCategory
from app.modules.gas_stations.models import GasStation
from app.modules.transactions.models import FraudLog, FraudRiskLevel, FraudActionTaken, FraudCaseStatus
from app.modules.transactions.service import TransactionService
from fastapi import HTTPException


@pytest.mark.anyio
async def test_automatic_fraud_logging_behavior():
    now = datetime.utcnow()
    kk = KK(code=f"KK-FRAUD-{uuid4().hex[:8]}")
    cashier_user = User(
        name="Fraud Logger Cashier",
        email=f"cashier-log-{uuid4().hex[:8]}@example.com",
        password="hashed_password",
        role=[UserRole.SALES_OFFICER],  # Cashier role associated with SPBU
        is_active=True,
    )
    buyer_user = User(
        name="Fraud Logger Buyer",
        email=f"buyer-log-{uuid4().hex[:8]}@example.com",
        password="hashed_password",
        role=[UserRole.BUYER],
        is_active=True,
    )
    buyer_profile = BuyerProfile(
        nik_snapshot="3171012345678901",
        ktp_nfc_id_snapshot=f"NFC-{uuid4().hex[:8]}",
        kk=kk,
        user=buyer_user,  # Buyer profile linked to the buyer user
        verification_status=VerificationStatus.VERIFIED,
        risk_score=Decimal("0.00"),
    )
    gas_station = GasStation(
        name="Fraud Testing Station",
        latitude=-6.200000,
        longitude=106.800000,
    )
    fuel_type = FuelType(
        name="Pertamax Non Subsidized",
        octane="92",
        category=FuelCategory.GASOLINE,
        price_per_liter=Decimal("13000.00"),
        subsidy_price_per_liter=Decimal("13000.00"),
        subsidy_type=SubsidyType.NON_SUBSIDIZED,  # Non-subsidized to skip KK eligibility check
    )
    registry_vehicle = VehicleRegistryMockup(
        plate_number="B 8888 FRD",
        registration_number=f"STNK-FRD-{uuid4().hex[:8]}",
        brand="Honda",
        vehicle_type="Civic",
        manufacture_year=2021,
        color="Merah",
        engine_capacity_cc=1498,
        pkb="4500000.00",
        njkb="280000000.00",
        owner_name="Fraud Logger User",
        owner_nik="3171012345678901",
    )
    ownership = VehicleOwnership(
        owner_type=VehicleOwnerType.BUYER_PROFILE,
        owner_id=None,  # Set dynamically in transaction
        vehicle_id=None,  # Set dynamically
        ownership_status=VehicleOwnershipStatus.PERSONAL,
        usage_type=VehicleUsageType.PERSONAL,
        quota_mode=VehicleQuotaMode.OWNER_PERSONAL_QUOTA,
        plate_number_snapshot="B 8888 FRD",
        ktp_nfc_id_snapshot="NFC-SNAPSHOT",
    )

    kk_id = None
    cashier_user_id = None
    buyer_user_id = None
    buyer_profile_id = None
    gas_station_id = None
    fuel_type_id = None
    vehicle_registry_id = None
    ownership_id = None

    try:
        # 1. Persist initial objects
        async with AsyncSessionLocal() as session:
            session.add_all([kk, gas_station, fuel_type, registry_vehicle])
            await session.commit()
            await session.refresh(kk)
            await session.refresh(gas_station)
            await session.refresh(fuel_type)
            await session.refresh(registry_vehicle)

            gas_station_id = gas_station.id
            fuel_type_id = fuel_type.id
            vehicle_registry_id = registry_vehicle.id

            # Cashier user must be associated with the SPBU
            cashier_user.gas_station_id = gas_station.id
            session.add(cashier_user)
            session.add(buyer_user)
            await session.commit()
            await session.refresh(cashier_user)
            await session.refresh(buyer_user)
            cashier_user_id = cashier_user.id
            buyer_user_id = buyer_user.id

            buyer_profile.kk_id = kk.id
            buyer_profile.user_id = buyer_user.id
            session.add(buyer_profile)
            await session.commit()
            await session.refresh(buyer_profile)
            buyer_profile_id = buyer_profile.id

            ownership.owner_id = buyer_profile.id
            ownership.vehicle_id = registry_vehicle.id
            session.add(ownership)
            await session.commit()
            await session.refresh(ownership)
            ownership_id = ownership.id

        # 2. Test TransactionService execution and mocking the fraud evaluation
        # We will use TransactionService and mock `_evaluate_fraud` to return dynamic scores
        async with AsyncSessionLocal() as session:
            service = TransactionService(db=session)

            # Class request mock
            class MockPurchaseRequest:
                plate_number = "B 8888 FRD"
                nik = "3171012345678901"
                gas_station_id = gas_station.id
                fuel_type_id = fuel_type.id
                liters = Decimal("25.00")
                total_amount = Decimal("325000.00")

            request = MockPurchaseRequest()

            # SCENARIO A: Fraud Evaluation returns SAFE (0 risk score)
            # Expected: Context completes, and NO FraudLog is generated.
            async def mock_eval_safe(*args, **kwargs):
                return {
                    "detected_frauds": [],
                    "risk_score": 0,
                    "risk_level": "SAFE",
                    "action": "ALLOW TRANSACTION"
                }

            service._evaluate_fraud = mock_eval_safe

            context = await service._prepare_fuel_purchase_context(
                current_user=cashier_user,
                request=request,
                require_wallet_payment=False
            )
            assert context["fraud_assessment"]["risk_score"] == 0

            # Verify no fraud log created
            result = await session.execute(
                select(FraudLog).filter(FraudLog.buyer_profile_id == buyer_profile.id)
            )
            assert len(result.scalars().all()) == 0

            # SCENARIO B: Fraud Evaluation returns SUSPICIOUS (risk score = 40)
            # Expected: Context completes without exception, but an automatic PENDING FraudLog is saved.
            async def mock_eval_suspicious(*args, **kwargs):
                return {
                    "detected_frauds": [{
                        "type": "RAPID_PURCHASE",
                        "points": 40,
                        "reason": "Pembelian terdeteksi berulang cepat."
                    }],
                    "risk_score": 40,
                    "risk_level": "SUSPICIOUS",
                    "action": "WARNING"
                }

            service._evaluate_fraud = mock_eval_suspicious

            context = await service._prepare_fuel_purchase_context(
                current_user=cashier_user,
                request=request,
                require_wallet_payment=False
            )
            assert context["fraud_assessment"]["risk_score"] == 40

            # We must commit or flush to database for the log to be saved in DB
            await session.commit()

            # Verify FraudLog was successfully created
            result = await session.execute(
                select(FraudLog).filter(FraudLog.buyer_profile_id == buyer_profile.id)
            )
            logs = result.scalars().all()
            assert len(logs) == 1
            log = logs[0]
            assert log.case_id.startswith("FR-")
            assert log.risk_score == 40
            assert log.risk_level == FraudRiskLevel.SUSPICIOUS
            assert log.action_taken == FraudActionTaken.WARNING
            assert log.status == FraudCaseStatus.PENDING
            assert log.plate_number_snapshot == "B 8888 FRD"
            # NIK snapshot is masked
            assert log.nik_snapshot is not None
            assert len(log.detected_frauds) == 1
            assert log.detected_frauds[0]["type"] == "RAPID_PURCHASE"

            # SCENARIO C: Fraud Evaluation returns HIGH_RISK (risk score = 80)
            # Expected: Context raises HTTPException, but an automatic HIGH_RISK FraudLog is still committed and saved in DB.
            async def mock_eval_high_risk(*args, **kwargs):
                return {
                    "detected_frauds": [{
                        "type": "MULTI_LOCATION_ABUSE",
                        "points": 80,
                        "reason": "Perpindahan lokasi tidak realistis."
                    }],
                    "risk_score": 80,
                    "risk_level": "HIGH_RISK",
                    "action": "FREEZE ACCOUNT"
                }

            service._evaluate_fraud = mock_eval_high_risk

            with pytest.raises(HTTPException) as exc_info:
                await service._prepare_fuel_purchase_context(
                    current_user=cashier_user,
                    request=request,
                    require_wallet_payment=False
                )
            assert exc_info.value.status_code == 400
            assert "dibekukan" in exc_info.value.detail

            # Verify the second FraudLog was created and committed even though exception was raised
            result = await session.execute(
                select(FraudLog).filter(
                    FraudLog.buyer_profile_id == buyer_profile.id,
                    FraudLog.risk_level == FraudRiskLevel.HIGH_RISK
                )
            )
            high_risk_logs = result.scalars().all()
            assert len(high_risk_logs) == 1
            high_risk_log = high_risk_logs[0]
            assert high_risk_log.risk_score == 80
            assert high_risk_log.action_taken == FraudActionTaken.FREEZE_ACCOUNT
            assert high_risk_log.status == FraudCaseStatus.PENDING

    finally:
        # Cleanup with strict dependency order
        async with AsyncSessionLocal() as session:
            from app.modules.wallets.models import Wallet
            if buyer_profile_id:
                await session.execute(delete(FraudLog).where(FraudLog.buyer_profile_id == buyer_profile_id))
            if ownership_id:
                await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id == ownership_id))
            if vehicle_registry_id:
                await session.execute(delete(VehicleRegistryMockup).where(VehicleRegistryMockup.id == vehicle_registry_id))
            if buyer_profile_id:
                await session.execute(delete(BuyerProfile).where(BuyerProfile.id == buyer_profile_id))
            if buyer_user_id:
                await session.execute(delete(Wallet).where(Wallet.owner_id == buyer_user_id))
            if cashier_user_id:
                await session.execute(delete(User).where(User.id == cashier_user_id))
            if buyer_user_id:
                await session.execute(delete(User).where(User.id == buyer_user_id))
            if fuel_type_id:
                await session.execute(delete(FuelType).where(FuelType.id == fuel_type_id))
            if gas_station_id:
                await session.execute(delete(GasStation).where(GasStation.id == gas_station_id))
            if kk_id:
                await session.execute(delete(KK).where(KK.id == kk_id))
            await session.commit()
