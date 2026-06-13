from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, require_roles
from app.modules.users.models import User, UserRole, BuyerProfile
from app.modules.companies.models import Company
from app.modules.vehicles.models import (
    VehicleOwnership,
    VehicleOwnerType,
    VehicleUsageType,
    VehicleQuotaMode,
    VehicleOwnershipStatus,
)
from app.modules.registries.models import VehicleRegistryMockup, VehicleClass
from app.modules.transactions.models import FuelTransaction, FuelTransactionStatus
from app.modules.subsidies.models import SubsidyQuota, SubsidyPolicy, SubsidyOwnerType
from app.modules.companies.schemas import (
    FleetSummaryResponse,
    FuelTrendItem,
    FleetVehicleListResponse,
    FleetVehicleItem,
    FleetVehicleCreateRequest,
    FleetVehicleAssignDriverRequest,
    FleetDriverItem,
    FleetLegalResponse,
    FleetProfileResponse,
    FleetVehicleTransactionListResponse,
    FleetVehicleTransactionItem,
)

router = APIRouter()


@router.get("/summary", response_model=FleetSummaryResponse)
async def get_fleet_summary(
    current_user: User = Depends(require_roles([UserRole.COMPANY_ADMIN])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with any company",
        )

    # 1. Total vehicles
    vehicles_count_stmt = select(func.count(VehicleOwnership.id)).filter(
        VehicleOwnership.owner_type == VehicleOwnerType.COMPANY,
        VehicleOwnership.owner_id == current_user.company_id,
    )
    total_vehicles = (await db.execute(vehicles_count_stmt)).scalar() or 0

    # 2. Active drivers count
    drivers_count_stmt = select(func.count(User.id)).filter(
        User.company_id == current_user.company_id,
        User.role.any(UserRole.BUYER),
    )
    active_drivers = (await db.execute(drivers_count_stmt)).scalar() or 0

    # 3. Monthly fuel consumption (liters)
    now = datetime.utcnow()
    start_of_month = datetime(now.year, now.month, 1)

    # Get company vehicle ownership ids
    ownership_stmt = select(VehicleOwnership.id).filter(
        VehicleOwnership.owner_type == VehicleOwnerType.COMPANY,
        VehicleOwnership.owner_id == current_user.company_id,
    )
    ownership_ids = (await db.execute(ownership_stmt)).scalars().all()

    monthly_consumption = 0.0
    if ownership_ids:
        consumption_stmt = select(func.sum(FuelTransaction.liters)).filter(
            or_(
                FuelTransaction.company_id == current_user.company_id,
                FuelTransaction.vehicle_ownership_id.in_(ownership_ids),
            ),
            FuelTransaction.transaction_status == FuelTransactionStatus.COMPLETED,
            FuelTransaction.created_at >= start_of_month,
        )
        monthly_consumption = float((await db.execute(consumption_stmt)).scalar() or 0.0)

    # 4. Remaining quota percentage
    # First get all company vehicles to look up their current month's quota
    vehicles_stmt = select(VehicleOwnership).filter(
        VehicleOwnership.owner_type == VehicleOwnerType.COMPANY,
        VehicleOwnership.owner_id == current_user.company_id,
    )
    company_vehicles = (await db.execute(vehicles_stmt)).scalars().all()

    # Get subsidy policies
    policies_stmt = select(SubsidyPolicy)
    policies = (await db.execute(policies_stmt)).scalars().all()
    policies_by_usage = {p.usage_type: p for p in policies}

    total_limit = Decimal("0")
    total_used = Decimal("0")

    if company_vehicles:
        vehicle_ids = [cv.vehicle_id for cv in company_vehicles]
        quotas_stmt = select(SubsidyQuota).filter(
            SubsidyQuota.owner_type == SubsidyOwnerType.VEHICLE,
            SubsidyQuota.owner_id.in_(vehicle_ids),
            SubsidyQuota.month == now.month,
            SubsidyQuota.year == now.year,
        )
        quotas_res = (await db.execute(quotas_stmt)).scalars().all()
        quotas_by_vehicle_id = {q.owner_id: q for q in quotas_res}

        for cv in company_vehicles:
            policy = policies_by_usage.get(cv.usage_type)
            limit = Decimal(policy.monthly_quota_liters) if policy else Decimal("200.00")
            quota = quotas_by_vehicle_id.get(cv.vehicle_id)
            used = Decimal(quota.used_liters) if quota else Decimal("0.00")

            total_limit += limit
            total_used += used

    remaining_quota_percent = 100
    if total_limit > 0:
        remaining_quota_percent = int(
            round(float((total_limit - total_used) / total_limit * 100))
        )
        # Bounded between 0 and 100
        remaining_quota_percent = max(0, min(100, remaining_quota_percent))

    # 5. Fuel consumption trend (last 6 months)
    fuel_trend = []
    for i in range(5, -1, -1):
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1

        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)

        monthly_trend_consumption = 0.0
        if ownership_ids:
            trend_stmt = select(func.sum(FuelTransaction.liters)).filter(
                or_(
                    FuelTransaction.company_id == current_user.company_id,
                    FuelTransaction.vehicle_ownership_id.in_(ownership_ids),
                ),
                FuelTransaction.transaction_status == FuelTransactionStatus.COMPLETED,
                FuelTransaction.created_at >= start_date,
                FuelTransaction.created_at < end_date,
            )
            monthly_trend_consumption = float(
                (await db.execute(trend_stmt)).scalar() or 0.0
            )

        month_label = start_date.strftime("%b")
        fuel_trend.append(FuelTrendItem(month=month_label, liters=monthly_trend_consumption))

    return FleetSummaryResponse(
        totalVehicles=total_vehicles,
        monthlyConsumption=monthly_consumption,
        activeDrivers=active_drivers,
        remainingQuotaPercent=remaining_quota_percent,
        fuelConsumptionTrend=fuel_trend,
    )


@router.get("/vehicles", response_model=FleetVehicleListResponse)
async def list_fleet_vehicles(
    current_user: User = Depends(require_roles([UserRole.COMPANY_ADMIN])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with any company",
        )

    # Fetch vehicle ownerships with joined/selected driver information
    vehicles_stmt = (
        select(VehicleOwnership)
        .options(selectinload(VehicleOwnership.assigned_user))
        .filter(
            VehicleOwnership.owner_type == VehicleOwnerType.COMPANY,
            VehicleOwnership.owner_id == current_user.company_id,
        )
        .order_by(VehicleOwnership.created_at.desc())
    )
    ownerships = (await db.execute(vehicles_stmt)).scalars().all()

    # Load registry details
    vehicle_ids = [o.vehicle_id for o in ownerships]
    registries_stmt = select(VehicleRegistryMockup).filter(
        VehicleRegistryMockup.id.in_(vehicle_ids)
    )
    registries_res = (await db.execute(registries_stmt)).scalars().all() if vehicle_ids else []
    registries_by_id = {r.id: r for r in registries_res}

    # Load quota details for current month
    now = datetime.utcnow()
    quotas_stmt = select(SubsidyQuota).filter(
        SubsidyQuota.owner_type == SubsidyOwnerType.VEHICLE,
        SubsidyQuota.owner_id.in_(vehicle_ids),
        SubsidyQuota.month == now.month,
        SubsidyQuota.year == now.year,
    )
    quotas_res = (await db.execute(quotas_stmt)).scalars().all() if vehicle_ids else []
    quotas_by_vehicle_id = {q.owner_id: q for q in quotas_res}

    # Load policies
    policies_stmt = select(SubsidyPolicy)
    policies = (await db.execute(policies_stmt)).scalars().all()
    policies_by_usage = {p.usage_type: p for p in policies}

    items = []
    for o in ownerships:
        reg = registries_by_id.get(o.vehicle_id)
        type_str = f"{reg.brand} {reg.vehicle_type}" if reg else o.usage_type.value
        driver_name = o.assigned_user.name if o.assigned_user else "Belum Ditugaskan"

        policy = policies_by_usage.get(o.usage_type)
        limit = float(policy.monthly_quota_liters) if policy else 200.0
        quota = quotas_by_vehicle_id.get(o.vehicle_id)
        used = float(quota.used_liters) if quota else 0.0

        items.append(
            FleetVehicleItem(
                id=o.id,
                plate=o.plate_number_snapshot,
                type=type_str,
                driver=driver_name,
                driver_id=o.assigned_user_id,
                status="Aktif",
                quotaLimit=limit,
                quotaUsed=used,
            )
        )

    return FleetVehicleListResponse(items=items, total=len(items))


@router.post("/vehicles", response_model=FleetVehicleItem)
async def register_fleet_vehicle(
    body: FleetVehicleCreateRequest,
    current_user: User = Depends(require_roles([UserRole.COMPANY_ADMIN])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with any company",
        )

    plate_clean = body.plate.strip().upper()

    # 1. Lookup plate number in VehicleRegistryMockup
    registry_stmt = select(VehicleRegistryMockup).filter(
        func.upper(VehicleRegistryMockup.plate_number) == plate_clean
    )
    registry_vehicle = (await db.execute(registry_stmt)).scalars().first()
    if not registry_vehicle:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plat nomor tidak ditemukan di database Kepolisian (Registry Mockup)",
        )

    # 2. Check if already registered
    existing_stmt = select(VehicleOwnership).filter(
        VehicleOwnership.vehicle_id == registry_vehicle.id
    )
    existing = (await db.execute(existing_stmt)).scalars().first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kendaraan dengan plat nomor ini sudah terdaftar",
        )

    # 3. Determine usage type based on registry
    usage_type = VehicleUsageType.COMMERCIAL_CAR
    if registry_vehicle.jenis == VehicleClass.TRUCK:
        usage_type = VehicleUsageType.COMMERCIAL_TRUCK
    elif registry_vehicle.jenis == VehicleClass.MOTORCYCLE:
        usage_type = VehicleUsageType.COMMERCIAL_MOTORCYCLE

    # Create VehicleOwnership
    ownership = VehicleOwnership(
        owner_type=VehicleOwnerType.COMPANY,
        owner_id=current_user.company_id,
        vehicle_id=registry_vehicle.id,
        ownership_status=VehicleOwnershipStatus.COMPANY,
        usage_type=usage_type,
        quota_mode=VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA,
        plate_number_snapshot=registry_vehicle.plate_number,
        ktp_nfc_id_snapshot=f"COMPANY-{str(current_user.company_id)[:8]}",
    )

    db.add(ownership)
    await db.flush()

    # Ensure SubsidyQuota exists for this month
    now = datetime.utcnow()
    policy_stmt = select(SubsidyPolicy).filter(SubsidyPolicy.usage_type == usage_type)
    policy = (await db.execute(policy_stmt)).scalars().first()
    limit = policy.monthly_quota_liters if policy else Decimal("200.00")

    quota = SubsidyQuota(
        owner_type=SubsidyOwnerType.VEHICLE,
        owner_id=registry_vehicle.id,
        subsidy_policy_id=policy.id if policy else None,
        month=now.month,
        year=now.year,
        quota_liters=limit,
        used_liters=Decimal("0.00"),
        is_active=True,
    )
    db.add(quota)
    await db.commit()
    await db.refresh(ownership)

    type_str = f"{registry_vehicle.brand} {registry_vehicle.vehicle_type}"

    return FleetVehicleItem(
        id=ownership.id,
        plate=ownership.plate_number_snapshot,
        type=type_str,
        driver="Belum Ditugaskan",
        driver_id=None,
        status="Aktif",
        quotaLimit=float(limit),
        quotaUsed=0.0,
    )


@router.delete("/vehicles/{ownership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fleet_vehicle(
    ownership_id: UUID,
    current_user: User = Depends(require_roles([UserRole.COMPANY_ADMIN])),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with any company",
        )

    stmt = select(VehicleOwnership).filter(
        VehicleOwnership.id == ownership_id,
        VehicleOwnership.owner_type == VehicleOwnerType.COMPANY,
        VehicleOwnership.owner_id == current_user.company_id,
    )
    ownership = (await db.execute(stmt)).scalars().first()
    if not ownership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kendaraan tidak ditemukan atau bukan milik perusahaan Anda",
        )

    await db.delete(ownership)
    await db.commit()
    return None


@router.get("/vehicles/{plate}/transactions", response_model=FleetVehicleTransactionListResponse)
async def get_fleet_vehicle_transactions(
    plate: str,
    current_user: User = Depends(require_roles([UserRole.COMPANY_ADMIN])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with any company",
        )

    # Verify vehicle ownership belongs to this company
    ownership_stmt = select(VehicleOwnership).filter(
        VehicleOwnership.plate_number_snapshot == plate,
        VehicleOwnership.owner_type == VehicleOwnerType.COMPANY,
        VehicleOwnership.owner_id == current_user.company_id,
    )
    ownership = (await db.execute(ownership_stmt)).scalars().first()
    if not ownership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kendaraan tidak ditemukan atau bukan milik perusahaan Anda",
        )

    # Fetch fuel transactions for this vehicle ownership
    tx_stmt = (
        select(FuelTransaction)
        .options(
            selectinload(FuelTransaction.buyer_profile).selectinload(BuyerProfile.user),
            selectinload(FuelTransaction.fuel_type),
            selectinload(FuelTransaction.gas_station),
        )
        .filter(FuelTransaction.vehicle_ownership_id == ownership.id)
        .order_by(FuelTransaction.created_at.desc())
    )
    transactions = (await db.execute(tx_stmt)).scalars().all()

    items = []
    for tx in transactions:
        driver_name = (
            tx.buyer_profile.user.name
            if tx.buyer_profile and tx.buyer_profile.user
            else "Unknown Driver"
        )
        fuel_name = tx.fuel_type.name if tx.fuel_type else "BBM"
        station_name = tx.gas_station.name if tx.gas_station else "SPBU"

        items.append(
            FleetVehicleTransactionItem(
                id=tx.id,
                date=tx.created_at.strftime("%Y-%m-%d %H:%M"),
                driver=driver_name,
                fuelType=fuel_name,
                liters=float(tx.liters),
                amount=float(tx.total_amount),
                station=station_name,
                status=tx.transaction_status.value,
            )
        )

    return FleetVehicleTransactionListResponse(items=items, total=len(items))


@router.get("/drivers", response_model=List[FleetDriverItem])
async def list_fleet_drivers(
    current_user: User = Depends(require_roles([UserRole.COMPANY_ADMIN])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with any company",
        )

    drivers_stmt = select(User).filter(
        User.company_id == current_user.company_id,
        User.role.any(UserRole.BUYER),
    )
    drivers = (await db.execute(drivers_stmt)).scalars().all()

    return [
        FleetDriverItem(id=d.id, name=d.name, email=d.email)
        for d in drivers
    ]


@router.put("/vehicles/{ownership_id}/assign-driver", response_model=FleetVehicleItem)
async def assign_fleet_vehicle_driver(
    ownership_id: UUID,
    body: FleetVehicleAssignDriverRequest,
    current_user: User = Depends(require_roles([UserRole.COMPANY_ADMIN])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with any company",
        )

    # Verify vehicle ownership belongs to company
    ownership_stmt = (
        select(VehicleOwnership)
        .options(selectinload(VehicleOwnership.assigned_user))
        .filter(
            VehicleOwnership.id == ownership_id,
            VehicleOwnership.owner_type == VehicleOwnerType.COMPANY,
            VehicleOwnership.owner_id == current_user.company_id,
        )
    )
    ownership = (await db.execute(ownership_stmt)).scalars().first()
    if not ownership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kendaraan tidak ditemukan atau bukan milik perusahaan Anda",
        )

    # Verify driver is in the same company
    if body.driver_id:
        driver_stmt = select(User).filter(
            User.id == body.driver_id,
            User.company_id == current_user.company_id,
            User.role.any(UserRole.BUYER),
        )
        driver = (await db.execute(driver_stmt)).scalars().first()
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver tidak ditemukan di perusahaan Anda",
            )
        ownership.assigned_user_id = body.driver_id
    else:
        ownership.assigned_user_id = None

    await db.commit()
    db.expire_all()

    # Re-fetch/refresh to load assigned driver's name
    ownership_stmt_refresh = (
        select(VehicleOwnership)
        .options(selectinload(VehicleOwnership.assigned_user))
        .filter(VehicleOwnership.id == ownership_id)
    )
    ownership = (await db.execute(ownership_stmt_refresh)).scalars().first()

    # Load registry details
    registry_stmt = select(VehicleRegistryMockup).filter(
        VehicleRegistryMockup.id == ownership.vehicle_id
    )
    reg = (await db.execute(registry_stmt)).scalars().first()
    type_str = f"{reg.brand} {reg.vehicle_type}" if reg else ownership.usage_type.value
    driver_name = ownership.assigned_user.name if ownership.assigned_user else "Belum Ditugaskan"

    # Load quota info
    now = datetime.utcnow()
    quota_stmt = select(SubsidyQuota).filter(
        SubsidyQuota.owner_type == SubsidyOwnerType.VEHICLE,
        SubsidyQuota.owner_id == ownership.vehicle_id,
        SubsidyQuota.month == now.month,
        SubsidyQuota.year == now.year,
    )
    quota = (await db.execute(quota_stmt)).scalars().first()
    used = float(quota.used_liters) if quota else 0.0

    policy_stmt = select(SubsidyPolicy).filter(
        SubsidyPolicy.usage_type == ownership.usage_type
    )
    policy = (await db.execute(policy_stmt)).scalars().first()
    limit = float(policy.monthly_quota_liters) if policy else 200.0

    return FleetVehicleItem(
        id=ownership.id,
        plate=ownership.plate_number_snapshot,
        type=type_str,
        driver=driver_name,
        driver_id=ownership.assigned_user_id,
        status="Aktif",
        quotaLimit=limit,
        quotaUsed=used,
    )


@router.get("/legal", response_model=FleetLegalResponse)
async def get_fleet_legal(
    current_user: User = Depends(require_roles([UserRole.COMPANY_ADMIN])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with any company",
        )

    company_stmt = select(Company).filter(Company.id == current_user.company_id)
    company = (await db.execute(company_stmt)).scalars().first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perusahaan tidak ditemukan",
        )

    return FleetLegalResponse(
        siup_no=company.siup_no,
        nib=company.nib,
        npwp_no=company.npwp_no,
        status=company.status,
    )


@router.get("/profile", response_model=FleetProfileResponse)
async def get_fleet_profile(
    current_user: User = Depends(require_roles([UserRole.COMPANY_ADMIN])),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with any company",
        )

    company_stmt = select(Company).filter(Company.id == current_user.company_id)
    company = (await db.execute(company_stmt)).scalars().first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perusahaan tidak ditemukan",
        )

    return FleetProfileResponse(
        name=company.name,
        email=company.email,
        phone=company.phone,
        fleet_size=company.fleet_size,
    )
