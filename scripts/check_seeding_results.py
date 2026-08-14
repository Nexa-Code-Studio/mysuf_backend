import asyncio
import sys
from pathlib import Path
from decimal import Decimal

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal
from app.modules.registries.models import VehicleRegistryMockup, CitizenRegistryMockup, KK
from app.modules.users.models import User, BuyerProfile
from app.modules.vehicles.models import VehicleOwnership, VehicleUsageType, VehicleQuotaMode
from app.modules.companies.models import Company
from app.modules.subsidies.models import SubsidyQuota
from app.modules.transactions.models import FuelTransaction
from app.modules.wallets.models import Wallet
from sqlalchemy import select, func

async def main():
    async with AsyncSessionLocal() as session:
        print("==================================================")
        print("           VERIFYING SEEDING RESULTS              ")
        print("==================================================")
        
        # 1. Check VehicleRegistryMockup
        res_v_mock = await session.execute(select(VehicleRegistryMockup))
        v_mocks = res_v_mock.scalars().all()
        print(f"\n[1] Vehicle Registry Mockups: {len(v_mocks)}")
        personal_mocks = [v for v in v_mocks if v.owner_nik is not None]
        fleet_mocks = [v for v in v_mocks if v.owner_nik is None and v.owner_name is not None]
        print(f"    - Personal Vehicles Seeded: {len(personal_mocks)}")
        print(f"    - Fleet Vehicles Seeded: {len(fleet_mocks)}")
        
        # 2. Check Companies Fleet Association
        res_companies = await session.execute(select(Company))
        companies = res_companies.scalars().all()
        print(f"\n[2] Company Fleet Verification:")
        for company in companies:
            stmt = select(func.count(VehicleOwnership.id)).where(
                VehicleOwnership.owner_type == "COMPANY",
                VehicleOwnership.owner_id == company.id
            )
            count_res = await session.execute(stmt)
            count = count_res.scalar()
            print(f"    - Company: {company.name} | Fleet Size: {count}")
            
            # Print details of fleet vehicles
            fleet_stmt = select(VehicleOwnership).where(
                VehicleOwnership.owner_type == "COMPANY",
                VehicleOwnership.owner_id == company.id
            )
            fleet_res = await session.execute(fleet_stmt)
            fleet_vehicles = fleet_res.scalars().all()
            for f_veh in fleet_vehicles[:3]: # print first 3
                print(f"        * Plate: {f_veh.plate_number_snapshot} | Usage: {f_veh.usage_type.name} | Quota Mode: {f_veh.quota_mode.name}")
            if len(fleet_vehicles) > 3:
                print(f"        * ... and {len(fleet_vehicles) - 3} more vehicles")

        # 3. Check Buyer Profiles & personal Vehicle Ownerships
        print(f"\n[3] Buyer Profiles & Vehicle Ownerships Verification:")
        res_users = await session.execute(
            select(User, BuyerProfile)
            .join(BuyerProfile, User.id == BuyerProfile.user_id)
        )
        buyers = res_users.all()
        print(f"    - Total verified buyers with profiles: {len(buyers)}")
        for user, profile in buyers:
            # Get associated vehicles
            stmt_v = select(VehicleOwnership).where(
                VehicleOwnership.owner_type == "BUYER_PROFILE",
                VehicleOwnership.owner_id == profile.id
            )
            res_v = await session.execute(stmt_v)
            vehicles = res_v.scalars().all()
            
            print(f"    - Buyer Name: {user.name} | Email: {user.email}")
            print(f"      Profile NIK Snapshot: {profile.nik_snapshot} | Vehicles Owned: {len(vehicles)}")
            for v in vehicles:
                print(f"        * Plate: {v.plate_number_snapshot} | Usage: {v.usage_type.name} | Quota Mode: {v.quota_mode.name}")

        # 4. Check Subsidy Quotas
        res_quotas = await session.execute(select(SubsidyQuota))
        quotas = res_quotas.scalars().all()
        print(f"\n[4] Subsidy Quotas: {len(quotas)}")
        active_quotas = [q for q in quotas if q.is_active]
        print(f"    - Active Quotas: {len(active_quotas)}")
        # Check if DEDICATED_VEHICLE_QUOTA ownerships have quota records
        res_dedicated = await session.execute(
            select(VehicleOwnership).where(VehicleOwnership.quota_mode == VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA)
        )
        dedicated_vehicles = res_dedicated.scalars().all()
        has_quota_count = 0
        for dv in dedicated_vehicles:
            stmt_dq = select(SubsidyQuota).where(
                SubsidyQuota.owner_type == "VEHICLE",
                SubsidyQuota.owner_id == dv.vehicle_id
            )
            dq_res = await session.execute(stmt_dq)
            if dq_res.scalars().first() is not None:
                has_quota_count += 1
        print(f"    - Dedicated Fleet/Usage Vehicles: {len(dedicated_vehicles)}")
        print(f"    - Dedicated Vehicles with Subsidy Quotas seeded: {has_quota_count}")

        # 5. Check Budi Pratama's wallet and transaction history
        print(f"\n[5] Budi's Demo History & Wallet:")
        budi_res = await session.execute(select(User).where(User.email == "budi.pratama@sidia.com"))
        budi = budi_res.scalars().first()
        if budi:
            # Get Budi's Wallet
            wallet_res = await session.execute(
                select(Wallet).where(Wallet.owner_type == "USER", Wallet.owner_id == budi.id)
            )
            budi_wallet = wallet_res.scalars().first()
            print(f"    - Wallet Balance: {budi_wallet.balance if budi_wallet else 'N/A'}")
            
            # Get Budi's Fuel Transactions
            profile_res = await session.execute(select(BuyerProfile).where(BuyerProfile.user_id == budi.id))
            budi_profile = profile_res.scalars().first()
            if budi_profile:
                tx_res = await session.execute(
                    select(FuelTransaction).where(FuelTransaction.buyer_profile_id == budi_profile.id).order_by(FuelTransaction.created_at.asc())
                )
                txs = tx_res.scalars().all()
                print(f"    - Fuel Transactions Count: {len(txs)}")
                for t in txs:
                    print(f"        * Time: {t.created_at} | Plate: {t.plate_number_snapshot} | Fuel: {t.liters}L | Amount: Rp{t.total_amount:,.2f} | Status: {t.transaction_status.name if hasattr(t.transaction_status, 'name') else t.transaction_status}")
            else:
                print("    - Buyer profile not found.")
        else:
            print("    - User budi.pratama@sidia.com not found.")
            
        print("\n==================================================")
        print("              VERIFICATION COMPLETED              ")
        print("==================================================")

if __name__ == "__main__":
    asyncio.run(main())
