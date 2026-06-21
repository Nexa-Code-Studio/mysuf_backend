import asyncio
import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import select, delete

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

TARGET_EMAIL = "ekya@mysuf.com"


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
    logger.info("Resetting fraud state for buyer: %s", TARGET_EMAIL)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).filter(User.email == TARGET_EMAIL)
        )
        user = result.scalars().first()
        if not user:
            logger.error("User '%s' not found. Has the seed been run?", TARGET_EMAIL)
            return

        buyer_profile = user.buyer_profile
        if not buyer_profile:
            logger.error("BuyerProfile not found for user '%s'.", TARGET_EMAIL)
            return

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

                logger.info("Deleted %d FuelTransaction(s) and related records.", len(fuel_tx_ids))

        # 7. Reset fraud fields on User and BuyerProfile
        user.is_blocked = False
        user.frozen_until = None
        buyer_profile.risk_score = 0
        buyer_profile.verification_status = VerificationStatus.VERIFIED

        await session.commit()

    logger.info("Reset complete — EKYA can now be used for another fraud demo run.")


if __name__ == "__main__":
    asyncio.run(main())
