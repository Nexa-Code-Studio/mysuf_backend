import asyncio
import logging
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid_extensions import uuid7

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import AsyncSessionLocal
from app.modules.transactions.models import (
    FuelTransaction,
    FuelTransactionStatus,
    PaymentMethod,
    BuyerType,
    FraudLog,
    FraudRiskLevel,
    FraudActionTaken,
    FraudCaseStatus,
)
from app.modules.users.models import BuyerProfile
from app.modules.gas_stations.models import GasStation
from app.modules.fuels.models import FuelType, SubsidyType
from app.modules.vehicles.models import VehicleOwnership
from app.modules.registries.models import CitizenRegistryMockup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DAYS_BACK = 60
TX_PER_STATION = 200
BATCH_SIZE = 500

SURABAYA_STATION_NAMES = [
    "SPBU Pertamina 44.501.01 (Surabaya Pusat)",
    "SPBU Pertamina 44.501.02 (Surabaya Timur)",
    "SPBU Pertamina 44.501.04 (Surabaya Selatan)",
    "SPBU Pertamina 44.509.01 (Jember)",
    "SPBU Pertamina 44.512.02 (Banyuwangi Ketapang)",
    "SPBU Pertamina 44.505.01 (Malang)",
]


async def main() -> None:
    logger.info("Starting transaction seeding (10,000 transactions)...")

    async with AsyncSessionLocal() as session:
        stations_result = await session.execute(select(GasStation))
        stations = stations_result.scalars().all()
        station_list = list(stations)
        logger.info("Loaded %d gas stations.", len(station_list))

        station_by_name = {s.name: s for s in station_list}
        surabaya_stations = [s for s in station_list if s.name in SURABAYA_STATION_NAMES]
        if not surabaya_stations and station_list:
            surabaya_stations = station_list[:6]

        fuels_result = await session.execute(select(FuelType))
        fuels = fuels_result.scalars().all()
        fuel_list = list(fuels)
        fuel_by_name = {f.name: f for f in fuel_list}
        logger.info("Loaded %d fuel types.", len(fuel_list))

        buyers_result = await session.execute(
            select(BuyerProfile)
        )
        buyers = buyers_result.scalars().all()
        logger.info("Loaded %d buyer profiles.", len(buyers))

        vehicles_result = await session.execute(select(VehicleOwnership))
        all_vehicles = vehicles_result.scalars().all()
        logger.info("Loaded %d vehicle ownerships.", len(all_vehicles))

        buyer_vehicles_map: dict = {}
        for v in all_vehicles:
            bid = str(v.owner_id)
            buyer_vehicles_map.setdefault(bid, []).append(v)

        buyer_nik_map: dict = {}
        for bp in buyers:
            buyer_nik_map[str(bp.id)] = bp.nik_snapshot

        now = datetime.utcnow()

        def random_date(days_back: int) -> datetime:
            days_ago = random.randint(0, days_back)
            d = now - timedelta(days=days_ago)
            if days_ago == 0:
                hour = random.randint(6, max(6, now.hour))
                if hour == now.hour:
                    minute = random.randint(0, max(0, now.minute))
                else:
                    minute = random.randint(0, 59)
            else:
                hour = random.randint(6, 20)
                minute = random.randint(0, 59)
            return d.replace(hour=hour, minute=minute, second=0, microsecond=0)

        def pick_vehicle(bp_id) -> tuple:
            bv = buyer_vehicles_map.get(str(bp_id), [])
            if not bv:
                return None, None
            v = random.choice(bv)
            return v, v.plate_number_snapshot

        def pick_fuel(vehicle) -> tuple:
            if vehicle and vehicle.usage_type and "MOTORCYCLE" in str(vehicle.usage_type):
                candidates = [f for f in fuel_list if "Pertalite" in f.name or "Pertamax" in f.name]
            else:
                candidates = fuel_list
            f = random.choice(candidates)
            return f

        def calc_total(fuel, liters):
            if fuel.subsidy_type == SubsidyType.SUBSIDIZED and fuel.subsidy_price_per_liter:
                return liters * fuel.subsidy_price_per_liter
            return liters * fuel.price_per_liter

        logger.info("Generating %d normal transactions...", TX_PER_STATION * len(station_list))
        normal_txs = []
        for station in station_list:
            for _ in range(TX_PER_STATION):
                bp = random.choice(buyers)
                vehicle, plate = pick_vehicle(bp.id)
                if not vehicle:
                    continue
                fuel = pick_fuel(vehicle)
                if not fuel:
                    continue
                is_mc = vehicle and vehicle.usage_type and "MOTORCYCLE" in str(vehicle.usage_type)
                liters = Decimal(str(random.randint(3 if is_mc else 10, 10 if is_mc else 50)))
                total = calc_total(fuel, liters)
                is_subsidized = fuel.subsidy_type == SubsidyType.SUBSIDIZED
                subsidized_liters = liters if is_subsidized else Decimal("0")
                non_subsidized_liters = Decimal("0") if is_subsidized else liters
                market_price = fuel.price_per_liter
                subsidy_price = fuel.subsidy_price_per_liter if is_subsidized else None
                created = random_date(DAYS_BACK)

                normal_txs.append(FuelTransaction(
                    id=uuid7(),
                    buyer_type=BuyerType.PERSONAL,
                    buyer_profile_id=bp.id,
                    vehicle_ownership_id=vehicle.id,
                    gas_station_id=station.id,
                    fuel_type_id=fuel.id,
                    liters=liters,
                    is_subsidized=is_subsidized,
                    subsidized_liters=subsidized_liters,
                    non_subsidized_liters=non_subsidized_liters,
                    market_price_per_liter=market_price,
                    subsidized_price_per_liter=subsidy_price,
                    total_amount=total,
                    payment_method=PaymentMethod.CASH,
                    transaction_status=FuelTransactionStatus.COMPLETED,
                    plate_number_snapshot=plate,
                    nik_snapshot=buyer_nik_map.get(str(bp.id)),
                    created_at=created,
                    updated_at=created,
                ))

        logger.info("Inserting %d normal transactions in batches...", len(normal_txs))
        for i in range(0, len(normal_txs), BATCH_SIZE):
            batch = normal_txs[i:i + BATCH_SIZE]
            session.add_all(batch)
            if (i // BATCH_SIZE) % 5 == 0:
                await session.flush()
                logger.info("  Inserted batch %d/%d...", i // BATCH_SIZE + 1, (len(normal_txs) - 1) // BATCH_SIZE + 1)
        await session.flush()
        logger.info("Normal transactions inserted.")

        logger.info("Creating fraud chains in Surabaya area...")
        fraud_logs = []
        fraud_extra_txs = []

        fraud_buyers = [bp for bp in buyers if str(bp.id) in buyer_vehicles_map and len(buyer_vehicles_map[str(bp.id)]) > 0]

        def make_fraud_tx(bp, vehicle, plate, station, fuel, liters, created, payment_method=PaymentMethod.CASH):
            total = calc_total(fuel, liters)
            is_subs = fuel.subsidy_type == SubsidyType.SUBSIDIZED
            return FuelTransaction(
                id=uuid7(),
                buyer_type=BuyerType.PERSONAL,
                buyer_profile_id=bp.id,
                vehicle_ownership_id=vehicle.id,
                gas_station_id=station.id,
                fuel_type_id=fuel.id,
                liters=liters,
                is_subsidized=is_subs,
                subsidized_liters=liters if is_subs else Decimal("0"),
                non_subsidized_liters=Decimal("0") if is_subs else liters,
                market_price_per_liter=fuel.price_per_liter,
                subsidized_price_per_liter=fuel.subsidy_price_per_liter if is_subs else None,
                total_amount=total,
                payment_method=payment_method,
                transaction_status=FuelTransactionStatus.COMPLETED,
                plate_number_snapshot=plate,
                nik_snapshot=buyer_nik_map.get(str(bp.id)),
                created_at=created,
                updated_at=created,
            )

        def make_fraud_log(bp, vehicle, plate, station, risk_score, risk_level, action, detected_frauds, tx_id=None, created=None):
            from uuid import uuid4
            return FraudLog(
                id=uuid7(),
                case_id=f"FR-{created.strftime('%y%m%d') if created else now.strftime('%y%m%d')}-{uuid4().hex[:6].upper()}",
                fuel_transaction_id=tx_id,
                gas_station_id=station.id if station else None,
                buyer_profile_id=bp.id if bp else None,
                vehicle_ownership_id=vehicle.id if vehicle else None,
                plate_number_snapshot=plate or "N/A",
                nik_snapshot=buyer_nik_map.get(str(bp.id)) if bp else None,
                risk_score=risk_score,
                risk_level=risk_level,
                action_taken=action,
                detected_frauds=detected_frauds,
                status=FraudCaseStatus.PENDING,
                created_at=created or now,
            )

        if surabaya_stations and fraud_buyers:
            far_stations = [s for s in station_list if s.name in [
                "SPBU Pertamina 44.512.02 (Banyuwangi Ketapang)",
                "SPBU Pertamina 44.509.01 (Jember)",
                "SPBU Pertamina 44.505.01 (Malang)",
            ]]
            if not far_stations:
                far_stations = station_list[6:9] if len(station_list) > 6 else station_list

            # 10x RAPID_PURCHASE chains (SUSPICIOUS, 25 pts)
            for _ in range(10):
                bp = random.choice(fraud_buyers)
                vehicle, plate = pick_vehicle(bp.id)
                if not vehicle:
                    continue
                fuel = pick_fuel(vehicle)
                base_time = random_date(7)
                liters = Decimal(str(random.randint(10, 30)))

                st = surabaya_stations[0] if surabaya_stations else station_list[0]
                tx_a = make_fraud_tx(bp, vehicle, plate, st, fuel, liters, base_time)
                fraud_extra_txs.append(tx_a)

                tx_b = make_fraud_tx(bp, vehicle, plate, st, fuel, liters, base_time + timedelta(minutes=random.randint(3, 15)))
                fraud_extra_txs.append(tx_b)

                fraud_logs.append(make_fraud_log(
                    bp, vehicle, plate, st,
                    risk_score=25, risk_level=FraudRiskLevel.SUSPICIOUS,
                    action=FraudActionTaken.WARNING,
                    detected_frauds=[{
                        "type": "RAPID_PURCHASE",
                        "points": 25,
                        "reason": f"Pembelian ulang kendaraan {plate} terjadi dalam waktu singkat di {st.name}."
                    }],
                    tx_id=tx_b.id, created=tx_b.created_at,
                ))

            # 5x MULTI_LOCATION_ABUSE chains (HIGH_RISK, 65 pts)
            for _ in range(5):
                bp = random.choice(fraud_buyers)
                vehicle, plate = pick_vehicle(bp.id)
                if not vehicle or not far_stations:
                    continue
                fuel = pick_fuel(vehicle)
                base_time = random_date(7)
                liters = Decimal(str(random.randint(10, 30)))

                local_st = surabaya_stations[0] if surabaya_stations else station_list[0]
                far_st = random.choice(far_stations)

                tx_a = make_fraud_tx(bp, vehicle, plate, local_st, fuel, liters, base_time)
                fraud_extra_txs.append(tx_a)
                tx_b = make_fraud_tx(bp, vehicle, plate, far_st, fuel, liters, base_time + timedelta(minutes=random.randint(5, 20)))
                fraud_extra_txs.append(tx_b)

                fraud_logs.append(make_fraud_log(
                    bp, vehicle, plate, far_st,
                    risk_score=65, risk_level=FraudRiskLevel.HIGH_RISK,
                    action=FraudActionTaken.FREEZE_ACCOUNT,
                    detected_frauds=[
                        {"type": "RAPID_PURCHASE", "points": 25,
                         "reason": f"Pembelian ulang kendaraan {plate} terjadi dalam waktu singkat."},
                        {"type": "MULTI_LOCATION_ABUSE", "points": 40,
                         "reason": f"Perpindahan kendaraan {plate} dari {local_st.name} ke {far_st.name} dalam waktu singkat tidak realistis."},
                    ],
                    tx_id=tx_b.id, created=tx_b.created_at,
                ))

            # 3x HOUSEHOLD_ABUSE (vehicle count, SUSPICIOUS, 35 pts)
            kk_groups = {}
            for bp in buyers:
                if bp.kk_id:
                    kk_groups.setdefault(str(bp.kk_id), []).append(bp)

            for kk_id, kk_buyers in kk_groups.items():
                if len(kk_buyers) < 2:
                    continue
                vehicles_in_kk = []
                for bp in kk_buyers:
                    bv = buyer_vehicles_map.get(str(bp.id), [])
                    vehicles_in_kk.extend(bv)
                if len(vehicles_in_kk) < 4:
                    continue

                abuse_day = random_date(14)
                selected_vehicles = random.sample(vehicles_in_kk, min(4, len(vehicles_in_kk)))
                for v in selected_vehicles:
                    bp_of_vehicle = next((b for b in kk_buyers if str(b.id) == str(v.owner_id)), kk_buyers[0])
                    fuel = pick_fuel(v)
                    liters = Decimal(str(random.randint(10, 30)))
                    st = random.choice(surabaya_stations) if surabaya_stations else random.choice(station_list)
                    tx = make_fraud_tx(bp_of_vehicle, v, v.plate_number_snapshot, st, fuel, liters, abuse_day + timedelta(hours=random.randint(6, 18)))
                    fraud_extra_txs.append(tx)

                representative_bp = kk_buyers[0]
                fraud_logs.append(make_fraud_log(
                    representative_bp, selected_vehicles[0], selected_vehicles[0].plate_number_snapshot,
                    surabaya_stations[0] if surabaya_stations else station_list[0],
                    risk_score=35, risk_level=FraudRiskLevel.SUSPICIOUS,
                    action=FraudActionTaken.WARNING,
                    detected_frauds=[{
                        "type": "HOUSEHOLD_ABUSE",
                        "points": 35,
                        "reason": f"Lebih dari 3 kendaraan dalam KK melakukan transaksi subsidi pada hari yang sama."
                    }],
                    created=abuse_day,
                ))
                break

        if fraud_extra_txs:
            session.add_all(fraud_extra_txs)
            await session.flush()
            logger.info("Inserted %d fraud chain transactions.", len(fraud_extra_txs))

        if fraud_logs:
            session.add_all(fraud_logs)
            await session.flush()
            logger.info("Inserted %d FraudLog entries.", len(fraud_logs))

        await session.commit()
        total_txs = len(normal_txs) + len(fraud_extra_txs)
        logger.info("Seeding complete!")
        logger.info("  Total transactions: %d", total_txs)
        logger.info("  FraudLog entries: %d", len(fraud_logs))
        logger.info("  Normal: %d | Fraud chains: %d", len(normal_txs), len(fraud_extra_txs))


if __name__ == "__main__":
    asyncio.run(main())
