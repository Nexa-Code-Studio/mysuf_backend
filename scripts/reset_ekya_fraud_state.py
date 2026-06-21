import asyncio
import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal
from app.modules.users.models import User, BuyerProfile, VerificationStatus
from app.modules.transactions.models import (
    FraudLog,
    FuelTransaction,
    PaymentTransaction,
    WalletTransaction,
    CashierScanEvent,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TARGET_EMAILS = ["ekya@mysuf.com", "ekyamuhammad@gmail.com"]
TARGET_NIK = "3511111411040003"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset EKYA's fraud state so the fraud demo can be replayed."
    )
    parser.add_argument(
        "--keep-transactions",
        action="store_true",
        help="Preserve transaction history (only reset fraud fields and logs).",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    logger.info("Resetting fraud state for buyer: %s / %s", TARGET_EMAILS, TARGET_NIK)

    async with AsyncSessionLocal() as session:
        # Find all buyer profiles matching NIK or emails
        stmt = (
            select(BuyerProfile)
            .outerjoin(User, User.id == BuyerProfile.user_id)
            .options(selectinload(BuyerProfile.user))
            .filter(
                (BuyerProfile.nik_snapshot == TARGET_NIK) |
                (User.email.in_(TARGET_EMAILS))
            )
        )
        result = await session.execute(stmt)
        buyer_profiles = result.scalars().all()

        if not buyer_profiles:
            # Also reset user status directly if they exist but don't have buyer profiles
            user_stmt = select(User).filter(User.email.in_(TARGET_EMAILS))
            user_res = await session.execute(user_stmt)
            users_without_profile = user_res.scalars().all()
            if users_without_profile:
                for u in users_without_profile:
                    u.is_blocked = False
                    u.frozen_until = None
                    logger.info("Reset user without profile: %s", u.email)
                await session.commit()
            logger.info("No BuyerProfiles found matching the search criteria.")
            return

        for buyer_profile in buyer_profiles:
            logger.info("Resetting BuyerProfile ID: %s, NIK: %s", buyer_profile.id, buyer_profile.nik_snapshot)
            
            # 1. Delete cashier scan events referencing this buyer
            await session.execute(
                delete(CashierScanEvent).filter(
                    CashierScanEvent.buyer_profile_id == buyer_profile.id
                )
            )

            # 2. Delete fraud logs referencing this buyer
            await session.execute(
                delete(FraudLog).filter(
                    FraudLog.buyer_profile_id == buyer_profile.id
                )
            )

            if not args.keep_transactions:
                # 3. Collect fuel transactions for this buyer
                tx_result = await session.execute(
                    select(FuelTransaction).filter(
                        FuelTransaction.buyer_profile_id == buyer_profile.id
                    )
                )
                fuel_txs = tx_result.scalars().all()
                fuel_tx_ids = [tx.id for tx in fuel_txs]

                if fuel_tx_ids:
                    # 4. Collect & delete payment transactions referencing these fuel tx
                    pay_result = await session.execute(
                        select(PaymentTransaction).filter(
                            PaymentTransaction.fuel_transaction_id.in_(fuel_tx_ids)
                        )
                    )
                    payment_txs = pay_result.scalars().all()
                    for pt in payment_txs:
                        # Delete wallet transactions that reference this payment tx
                        await session.execute(
                            delete(WalletTransaction).filter(
                                WalletTransaction.payment_transaction_id == pt.id
                            )
                        )
                        await session.delete(pt)

                    # 5. Detach wallet tx refs from fuel txs, then delete orphaned wallet txs
                    for ft in fuel_txs:
                        wt_id = ft.wallet_transaction_id
                        ft.wallet_transaction_id = None
                        if wt_id:
                            wt = await session.get(WalletTransaction, wt_id)
                            if wt:
                                await session.delete(wt)

                    # 6. Delete fuel transactions
                    for ft in fuel_txs:
                        await session.delete(ft)

                    logger.info("Deleted %d FuelTransaction(s) and related records for BuyerProfile ID: %s.", len(fuel_tx_ids), buyer_profile.id)

            # 7. Reset fraud fields on User and BuyerProfile
            buyer_profile.risk_score = 0
            buyer_profile.verification_status = VerificationStatus.VERIFIED
            
            if buyer_profile.user:
                buyer_profile.user.is_blocked = False
                buyer_profile.user.frozen_until = None
                logger.info("Reset linked User: %s", buyer_profile.user.email)

        await session.commit()

    logger.info("Reset complete — EKYA can now be used for another fraud demo run.")

    logger.info("Reset complete — EKYA can now be used for another fraud demo run.")


if __name__ == "__main__":
    asyncio.run(main())
