import asyncio
import logging
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid_extensions import uuid7

# Resolve project root dynamically
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal
from app.modules.users.models import User, BuyerProfile
from app.modules.wallets.models import Wallet, OwnerType
from app.modules.transactions.models import (
    FuelTransaction,
    FuelTransactionStatus,
    PaymentMethod,
    BuyerType,
    TransactionType,
    TransactionFlow,
    WalletTransactionStatus,
    WalletTransaction
)
from app.modules.fuels.models import FuelType, SubsidyType
from app.modules.subsidies.models import SubsidyQuota, SubsidyOwnerType
from sqlalchemy import select, delete

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def seed_demo_history() -> None:
    logger.info("==================================================")
    logger.info("STARTING DEMO HISTORY SEEDING FOR BUDI & SO...")
    logger.info("==================================================")

    async with AsyncSessionLocal() as session:
        # 1. Fetch Sales Officer (Cashier)
        res_so = await session.execute(
            select(User).filter(User.email == "so@sidia.id")
        )
        sales_officer = res_so.scalars().first()
        if not sales_officer:
            logger.error("Sales Officer 'so@sidia.id' not found! Make sure to run reset.sh first.")
            return

        if not sales_officer.gas_station_id:
            logger.error("Sales Officer 'so@sidia.id' is not associated with any gas station.")
            return

        # 2. Fetch Buyer (Budi)
        res_buyer = await session.execute(
            select(User).filter(User.email == "budi.pratama@sidia.com")
        )
        buyer_user = res_buyer.scalars().first()
        if not buyer_user:
            logger.error("Buyer 'budi.pratama@sidia.com' not found!")
            return

        res_profile = await session.execute(
            select(BuyerProfile).filter(BuyerProfile.user_id == buyer_user.id)
        )
        buyer_profile = res_profile.scalars().first()
        if not buyer_profile:
            logger.error("BuyerProfile not found for 'budi.pratama@sidia.com'!")
            return

        # 3. Fetch Wallet
        res_wallet = await session.execute(
            select(Wallet).filter(
                Wallet.owner_id == buyer_user.id,
                Wallet.owner_type == OwnerType.USER
            )
        )
        wallet = res_wallet.scalars().first()
        if not wallet:
            logger.error("Wallet not found for buyer!")
            return

        # 4. Fetch Fuel Types
        res_fuels = await session.execute(select(FuelType))
        fuels = {f.name: f for f in res_fuels.scalars().all()}

        pertalite = fuels.get("Pertalite")
        solar_subsidi = fuels.get("Solar Subsidi") or fuels.get("Solar")
        pertamax = fuels.get("Pertamax")

        if not pertalite or not pertamax:
            logger.error("Pertalite or Pertamax fuel types not found!")
            return

        # 5. Clean up existing transactions for this buyer's wallet & profile to allow clean re-runs
        await session.execute(
            delete(FuelTransaction).where(FuelTransaction.buyer_profile_id == buyer_profile.id)
        )
        await session.execute(
            delete(WalletTransaction).where(WalletTransaction.wallet_id == wallet.id)
        )
        await session.commit()
        logger.info("Cleaned up existing transactions for 'budi.pratama@sidia.com' successfully.")

        # 6. Define transaction sequence (oldest first)
        now = datetime.utcnow()
        
        # We start with a balance of Rp 150.000
        balance = Decimal("150000.00")
        
        # Transaction 1: Top Up +200k, 5 days ago
        t1_time = now - timedelta(days=5, hours=3)
        w_tx1 = WalletTransaction(
            wallet_id=wallet.id,
            type=TransactionType.TOP_UP,
            transaction_flow=TransactionFlow.IN,
            amount=Decimal("200000.00"),
            balance_before=balance,
            balance_after=balance + Decimal("200000.00"),
            description="Top Up via Xendit VA Bank Mandiri",
            status=WalletTransactionStatus.SUCCESS,
            created_at=t1_time
        )
        session.add(w_tx1)
        balance += Decimal("200000.00")

        # Transaction 2: Fuel Purchase (Pertalite Subsidized) via Wallet, 4 days ago
        # 15 Liters of Pertalite @ Rp 6.500 = Rp 97.500
        t2_time = now - timedelta(days=4, hours=2)
        w_tx2 = WalletTransaction(
            wallet_id=wallet.id,
            type=TransactionType.FUEL_PURCHASE,
            transaction_flow=TransactionFlow.OUT,
            amount=Decimal("97500.00"),
            balance_before=balance,
            balance_after=balance - Decimal("97500.00"),
            description=f"Pembelian Pertalite - N 1234 AB",
            status=WalletTransactionStatus.SUCCESS,
            created_at=t2_time
        )
        session.add(w_tx2)
        await session.flush()
        
        f_tx2 = FuelTransaction(
            buyer_type=BuyerType.PERSONAL,
            buyer_profile_id=buyer_profile.id,
            gas_station_id=sales_officer.gas_station_id,
            fuel_type_id=pertalite.id,
            liters=Decimal("15.00"),
            is_subsidized=True,
            subsidized_liters=Decimal("15.00"),
            non_subsidized_liters=Decimal("0.00"),
            market_price_per_liter=Decimal("10000.00"),
            subsidized_price_per_liter=Decimal("6500.00"),
            total_amount=Decimal("97500.00"),
            payment_method=PaymentMethod.WALLET,
            wallet_transaction_id=w_tx2.id,
            transaction_status=FuelTransactionStatus.COMPLETED,
            verified_by_user_id=sales_officer.id,
            plate_number_snapshot="N 1234 AB",
            nik_snapshot=buyer_profile.nik_snapshot,
            created_at=t2_time
        )
        session.add(f_tx2)
        balance -= Decimal("97500.00")

        # Transaction 3: Top Up +200k, 3 days ago
        t3_time = now - timedelta(days=3, hours=4)
        w_tx3 = WalletTransaction(
            wallet_id=wallet.id,
            type=TransactionType.TOP_UP,
            transaction_flow=TransactionFlow.IN,
            amount=Decimal("200000.00"),
            balance_before=balance,
            balance_after=balance + Decimal("200000.00"),
            description="Top Up via QRIS ShopeePay",
            status=WalletTransactionStatus.SUCCESS,
            created_at=t3_time
        )
        session.add(w_tx3)
        balance += Decimal("200000.00")

        # Transaction 4: Fuel Purchase (Solar Subsidi) via Cash, 3 days ago
        # 10 Liters of Solar @ Rp 5.150 = Rp 51.500 (Does not deduct wallet)
        t4_time = now - timedelta(days=3, hours=1)
        f_tx4 = FuelTransaction(
            buyer_type=BuyerType.PERSONAL,
            buyer_profile_id=buyer_profile.id,
            gas_station_id=sales_officer.gas_station_id,
            fuel_type_id=solar_subsidi.id if solar_subsidi else pertalite.id,
            liters=Decimal("10.00"),
            is_subsidized=True,
            subsidized_liters=Decimal("10.00"),
            non_subsidized_liters=Decimal("0.00"),
            market_price_per_liter=Decimal("6800.00"),
            subsidized_price_per_liter=Decimal("5150.00"),
            total_amount=Decimal("51500.00"),
            payment_method=PaymentMethod.CASH,
            transaction_status=FuelTransactionStatus.COMPLETED,
            verified_by_user_id=sales_officer.id,
            plate_number_snapshot="L 9876 CD",
            nik_snapshot=buyer_profile.nik_snapshot,
            created_at=t4_time
        )
        session.add(f_tx4)

        # Transaction 5: Fuel Purchase (Pertamax Non-Subsidized) via Wallet, 2 days ago
        # 5 Liters of Pertamax @ Rp 13.900 = Rp 69.500
        t5_time = now - timedelta(days=2, hours=5)
        w_tx5 = WalletTransaction(
            wallet_id=wallet.id,
            type=TransactionType.FUEL_PURCHASE,
            transaction_flow=TransactionFlow.OUT,
            amount=Decimal("69500.00"),
            balance_before=balance,
            balance_after=balance - Decimal("69500.00"),
            description=f"Pembelian Pertamax - N 1234 AB",
            status=WalletTransactionStatus.SUCCESS,
            created_at=t5_time
        )
        session.add(w_tx5)
        await session.flush()

        f_tx5 = FuelTransaction(
            buyer_type=BuyerType.PERSONAL,
            buyer_profile_id=buyer_profile.id,
            gas_station_id=sales_officer.gas_station_id,
            fuel_type_id=pertamax.id,
            liters=Decimal("5.00"),
            is_subsidized=False,
            subsidized_liters=Decimal("0.00"),
            non_subsidized_liters=Decimal("5.00"),
            market_price_per_liter=Decimal("13900.00"),
            total_amount=Decimal("69500.00"),
            payment_method=PaymentMethod.WALLET,
            wallet_transaction_id=w_tx5.id,
            transaction_status=FuelTransactionStatus.COMPLETED,
            verified_by_user_id=sales_officer.id,
            plate_number_snapshot="N 1234 AB",
            nik_snapshot=buyer_profile.nik_snapshot,
            created_at=t5_time
        )
        session.add(f_tx5)
        balance -= Decimal("69500.00")

        # Transaction 6: Fuel Purchase (Pertalite Subsidized) via Wallet, yesterday
        # 12 Liters of Pertalite @ Rp 6.500 = Rp 78.000
        t6_time = now - timedelta(days=1, hours=2)
        w_tx6 = WalletTransaction(
            wallet_id=wallet.id,
            type=TransactionType.FUEL_PURCHASE,
            transaction_flow=TransactionFlow.OUT,
            amount=Decimal("78000.00"),
            balance_before=balance,
            balance_after=balance - Decimal("78000.00"),
            description=f"Pembelian Pertalite - N 1234 AB",
            status=WalletTransactionStatus.SUCCESS,
            created_at=t6_time
        )
        session.add(w_tx6)
        await session.flush()

        f_tx6 = FuelTransaction(
            buyer_type=BuyerType.PERSONAL,
            buyer_profile_id=buyer_profile.id,
            gas_station_id=sales_officer.gas_station_id,
            fuel_type_id=pertalite.id,
            liters=Decimal("12.00"),
            is_subsidized=True,
            subsidized_liters=Decimal("12.00"),
            non_subsidized_liters=Decimal("0.00"),
            market_price_per_liter=Decimal("10000.00"),
            subsidized_price_per_liter=Decimal("6500.00"),
            total_amount=Decimal("78000.00"),
            payment_method=PaymentMethod.WALLET,
            wallet_transaction_id=w_tx6.id,
            transaction_status=FuelTransactionStatus.COMPLETED,
            verified_by_user_id=sales_officer.id,
            plate_number_snapshot="N 1234 AB",
            nik_snapshot=buyer_profile.nik_snapshot,
            created_at=t6_time
        )
        session.add(f_tx6)
        balance -= Decimal("78000.00")

        # Transaction 7: Fuel Purchase (Solar Subsidi) via Wallet, today
        # 8 Liters of Solar @ Rp 5.150 = Rp 41.200
        t7_time = now - timedelta(minutes=45)
        w_tx7 = WalletTransaction(
            wallet_id=wallet.id,
            type=TransactionType.FUEL_PURCHASE,
            transaction_flow=TransactionFlow.OUT,
            amount=Decimal("41200.00"),
            balance_before=balance,
            balance_after=balance - Decimal("41200.00"),
            description=f"Pembelian Solar Subsidi - N 1234 AB",
            status=WalletTransactionStatus.SUCCESS,
            created_at=t7_time
        )
        session.add(w_tx7)
        await session.flush()

        f_tx7 = FuelTransaction(
            buyer_type=BuyerType.PERSONAL,
            buyer_profile_id=buyer_profile.id,
            gas_station_id=sales_officer.gas_station_id,
            fuel_type_id=solar_subsidi.id if solar_subsidi else pertalite.id,
            liters=Decimal("8.00"),
            is_subsidized=True,
            subsidized_liters=Decimal("8.00"),
            non_subsidized_liters=Decimal("0.00"),
            market_price_per_liter=Decimal("6800.00"),
            subsidized_price_per_liter=Decimal("5150.00"),
            total_amount=Decimal("41200.00"),
            payment_method=PaymentMethod.WALLET,
            wallet_transaction_id=w_tx7.id,
            transaction_status=FuelTransactionStatus.COMPLETED,
            verified_by_user_id=sales_officer.id,
            plate_number_snapshot="N 1234 AB",
            nik_snapshot=buyer_profile.nik_snapshot,
            created_at=t7_time
        )
        session.add(f_tx7)
        balance -= Decimal("41200.00")

        # 7. Update Wallet Balance to the final calculated balance
        wallet.balance = balance
        logger.info(f"Updated Wallet balance of 'budi.pratama@sidia.com' to {balance}")

        # 8. Update Quota used liters for current month (August 2026)
        # Seeded subsidized transactions in August 2026:
        # - Tx 2 (15L) - Tx 4 (10L) - Tx 6 (12L) - Tx 7 (8L)
        # Total = 45L.
        res_quota = await session.execute(
            select(SubsidyQuota).filter(
                SubsidyQuota.owner_type == SubsidyOwnerType.BUYER_PROFILE,
                SubsidyQuota.owner_id == buyer_profile.id,
                SubsidyQuota.month == now.month,
                SubsidyQuota.year == now.year
            )
        )
        quota = res_quota.scalars().first()
        if quota:
            quota.used_liters = Decimal("45.00")
            logger.info(f"Updated Subsidy Quota used_liters to 45.0L for {now.month}/{now.year}")
        else:
            # Fallback if no quota exists yet (highly unlikely since master seeds it)
            quota = SubsidyQuota(
                owner_type=SubsidyOwnerType.BUYER_PROFILE,
                owner_id=buyer_profile.id,
                month=now.month,
                year=now.year,
                quota_liters=Decimal("150.00"),
                used_liters=Decimal("45.00"),
                is_active=True
            )
            session.add(quota)
            logger.info("Created and seeded new Subsidy Quota record.")

        await session.commit()
        logger.info("==================================================")
        logger.info("DEMO HISTORY SEEDING COMPLETED SUCCESSFULLY!")
        logger.info("==================================================")

if __name__ == "__main__":
    asyncio.run(seed_demo_history())
