from typing import Any
from decimal import Decimal
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_, func
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, require_roles
from app.modules.users.models import User, UserRole, BuyerProfile
from app.modules.registries.models import KK, VehicleRegistryMockup
from app.modules.subsidies.models import KKSubsidyEligibility, SubsidyPolicy, EligibilityStatus
from app.modules.vehicles.models import VehicleUsageType, VehicleOwnership, VehicleOwnerType
from app.modules.vehicles.service import VehicleService
from app.modules.transactions.service import TransactionService
from app.modules.subsidies.schemas import (
    KKEligibilityListResponse,
    KKEligibilityItem,
    ThresholdUpdateRequest,
    GovernmentQuotaPoliciesResponse,
    GovernmentQuotaPoliciesUpdate,
    GovernmentQuotaTransactionResponse,
    GovernmentQuotaTransactionItem,
    BlacklistListResponse,
    BlacklistItem,
    BlacklistCreateRequest,
)

router = APIRouter()


@router.get("/summary")
async def get_government_dashboard_summary(
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    service = TransactionService(db)
    return await service.get_government_dashboard_summary(current_user)


@router.get("/heatmap")
async def get_government_heatmap(
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    service = TransactionService(db)
    return await service.get_government_heatmap_data(current_user)


@router.get("/eligibility", response_model=KKEligibilityListResponse)
async def get_government_eligibility(
    page: int = Query(1, ge=1),
    size: int = Query(8, ge=1, le=100),
    q: str | None = Query(None),
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    # Fetch PERSONAL policy for threshold and eligibility lookup
    policy_stmt = select(SubsidyPolicy).filter(SubsidyPolicy.usage_type == VehicleUsageType.PERSONAL)
    policy = (await db.execute(policy_stmt)).scalars().first()
    threshold = policy.max_allowed_njkb if policy else Decimal("300000000.00")

    # Base query for KK
    stmt = select(KK)
    if q:
        # Filter by KK code
        stmt = stmt.filter(KK.code.ilike(f"%{q}%"))

    # Execute and paginate
    result = await db.execute(stmt)
    kks = result.scalars().all()

    items = []
    for kk in kks:
        # Find buyer profile IDs in this KK
        bp_stmt = select(BuyerProfile.id).filter(BuyerProfile.kk_id == kk.id)
        bp_ids = (await db.execute(bp_stmt)).scalars().all()

        # Count unique vehicles in VehicleOwnership
        if bp_ids:
            v_stmt = select(func.count(func.distinct(VehicleOwnership.vehicle_id))).filter(
                VehicleOwnership.owner_type == VehicleOwnerType.BUYER_PROFILE,
                VehicleOwnership.owner_id.in_(bp_ids)
            )
            vehicle_count = (await db.execute(v_stmt)).scalar() or 0
        else:
            vehicle_count = 0

        # Fetch latest KKSubsidyEligibility
        if policy:
            elig_stmt = select(KKSubsidyEligibility).filter(
                KKSubsidyEligibility.kk_id == kk.id,
                KKSubsidyEligibility.subsidy_policy_id == policy.id
            ).order_by(KKSubsidyEligibility.checked_at.desc(), KKSubsidyEligibility.id.desc()).limit(1)
            elig = (await db.execute(elig_stmt)).scalars().first()
        else:
            elig = None

        if elig:
            total_njkb = elig.total_njkb
            is_eligible = elig.eligibility_status == EligibilityStatus.ELIGIBLE
        else:
            # Fallback recompute dynamically
            total_njkb = Decimal("0")
            if bp_ids:
                v_ids_stmt = select(func.distinct(VehicleOwnership.vehicle_id)).filter(
                    VehicleOwnership.owner_type == VehicleOwnerType.BUYER_PROFILE,
                    VehicleOwnership.owner_id.in_(bp_ids)
                )
                unique_vehicle_ids = (await db.execute(v_ids_stmt)).scalars().all()
                for vid in unique_vehicle_ids:
                    reg_stmt = select(VehicleRegistryMockup.njkb).filter(VehicleRegistryMockup.id == vid)
                    njkb_val = (await db.execute(reg_stmt)).scalar()
                    if njkb_val:
                        total_njkb += Decimal(njkb_val)
            is_eligible = total_njkb <= threshold

        items.append(
            KKEligibilityItem(
                id=elig.id if elig else kk.id,
                kk_id=kk.id,
                code=kk.code,
                vehicle_count=vehicle_count,
                total_njkb=total_njkb,
                threshold=threshold,
                eligible="Ya" if is_eligible else "Tidak"
            )
        )

    # Manual slicing for simplicity in API pagination
    total = len(items)
    eligible_count = sum(1 for item in items if item.eligible == "Ya")
    ineligible_count = total - eligible_count
    
    start = (page - 1) * size
    end = start + size
    paginated_items = items[start:end]

    return {
        "items": paginated_items,
        "total": total,
        "page": page,
        "size": size,
        "eligible_count": eligible_count,
        "ineligible_count": ineligible_count,
        "threshold": threshold
    }


@router.put("/eligibility/threshold")
async def update_government_eligibility_threshold(
    http_request: Request,
    request: ThresholdUpdateRequest,
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    policy_stmt = select(SubsidyPolicy).filter(SubsidyPolicy.usage_type == VehicleUsageType.PERSONAL)
    policy = (await db.execute(policy_stmt)).scalars().first()
    if not policy:
        raise HTTPException(status_code=404, detail="Personal subsidy policy not found")

    policy.max_allowed_njkb = request.threshold
    await db.commit()
    await db.refresh(policy)

    # Recalculate eligibility for ALL KKs in the database
    kk_stmt = select(KK)
    kks = (await db.execute(kk_stmt)).scalars().all()
    for kk in kks:
        bp_stmt = select(BuyerProfile).filter(BuyerProfile.kk_id == kk.id)
        buyer_profiles = (await db.execute(bp_stmt)).scalars().all()
        if not buyer_profiles:
            continue
        vehicle_service = VehicleService(db)
        await vehicle_service._recompute_kk_subsidy_eligibility(buyer_profiles[0].id)

    await db.commit()

    # Audit logging
    from app.modules.system_audit_logs.service import SystemAuditLogService
    ip = SystemAuditLogService.resolve_ip(http_request)
    audit_svc = SystemAuditLogService(db)
    
    # Format NJKB threshold amount nicely (e.g. 300.000.000)
    formatted_val = f"Rp {int(policy.max_allowed_njkb):,}".replace(",", ".")
    await audit_svc.log_action(
        actor=current_user,
        action=f"Update bobot kelayakan: NJKB {formatted_val}",
        ip_address=ip
    )

    return {"threshold": int(policy.max_allowed_njkb)}


@router.get("/quota-policies", response_model=GovernmentQuotaPoliciesResponse)
async def get_government_quota_policies(
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    policies_stmt = select(SubsidyPolicy).filter(
        SubsidyPolicy.usage_type.in_([
            VehicleUsageType.PERSONAL,
            VehicleUsageType.COMMERCIAL_MOTORCYCLE,
            VehicleUsageType.COMMERCIAL_CAR,
            VehicleUsageType.COMMERCIAL_TRUCK
        ])
    )
    policies = (await db.execute(policies_stmt)).scalars().all()
    policies_map = {p.usage_type: p.monthly_quota_liters for p in policies}

    return {
        "warga": policies_map.get(VehicleUsageType.PERSONAL, Decimal("250.00")),
        "motor_komersial": policies_map.get(VehicleUsageType.COMMERCIAL_MOTORCYCLE, Decimal("100.00")),
        "mobil_komersial": policies_map.get(VehicleUsageType.COMMERCIAL_CAR, Decimal("250.00")),
        "truk_komersial": policies_map.get(VehicleUsageType.COMMERCIAL_TRUCK, Decimal("500.00"))
    }


@router.put("/quota-policies")
async def update_government_quota_policies(
    http_request: Request,
    request: GovernmentQuotaPoliciesUpdate,
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    # Update PERSONAL
    policy_p = (await db.execute(select(SubsidyPolicy).filter(SubsidyPolicy.usage_type == VehicleUsageType.PERSONAL))).scalars().first()
    if policy_p:
        policy_p.monthly_quota_liters = request.warga

    # Update COMMERCIAL_MOTORCYCLE
    policy_mm = (await db.execute(select(SubsidyPolicy).filter(SubsidyPolicy.usage_type == VehicleUsageType.COMMERCIAL_MOTORCYCLE))).scalars().first()
    if policy_mm:
        policy_mm.monthly_quota_liters = request.motor_komersial

    # Update COMMERCIAL_CAR
    policy_cc = (await db.execute(select(SubsidyPolicy).filter(SubsidyPolicy.usage_type == VehicleUsageType.COMMERCIAL_CAR))).scalars().first()
    if policy_cc:
        policy_cc.monthly_quota_liters = request.mobil_komersial

    # Update COMMERCIAL_TRUCK
    policy_ct = (await db.execute(select(SubsidyPolicy).filter(SubsidyPolicy.usage_type == VehicleUsageType.COMMERCIAL_TRUCK))).scalars().first()
    if policy_ct:
        policy_ct.monthly_quota_liters = request.truk_komersial

    await db.commit()

    # Audit logging
    from app.modules.system_audit_logs.service import SystemAuditLogService
    ip = SystemAuditLogService.resolve_ip(http_request)
    audit_svc = SystemAuditLogService(db)
    
    action = (
        f"Update kebijakan kuota bulanan: Warga {int(request.warga)}L, "
        f"Motor {int(request.motor_komersial)}L, Mobil {int(request.mobil_komersial)}L, "
        f"Truk {int(request.truk_komersial)}L"
    )
    await audit_svc.log_action(
        actor=current_user,
        action=action,
        ip_address=ip
    )

    return {"status": "success"}


@router.get("/quota-transactions", response_model=GovernmentQuotaTransactionResponse)
async def get_government_quota_transactions(
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    # Pre-query policies
    policies_stmt = select(SubsidyPolicy)
    policies = (await db.execute(policies_stmt)).scalars().all()
    p_map = {p.usage_type: p.monthly_quota_liters for p in policies}

    warga_quota = p_map.get(VehicleUsageType.PERSONAL, Decimal("250.00"))
    motor_quota = p_map.get(VehicleUsageType.COMMERCIAL_MOTORCYCLE, Decimal("100.00"))
    car_quota = p_map.get(VehicleUsageType.COMMERCIAL_CAR, Decimal("250.00"))
    truck_quota = p_map.get(VehicleUsageType.COMMERCIAL_TRUCK, Decimal("500.00"))

    # Fetch Buyer Profiles
    stmt = select(BuyerProfile).options(selectinload(BuyerProfile.user))
    profiles = (await db.execute(stmt)).scalars().all()

    items = []
    for profile in profiles:
        if not profile.user:
            continue

        # Fetch vehicles for this profile
        v_stmt = select(VehicleOwnership).filter(
            VehicleOwnership.owner_type == VehicleOwnerType.BUYER_PROFILE,
            VehicleOwnership.owner_id == profile.id
        )
        ownerships = (await db.execute(v_stmt)).scalars().all()

        # Check vehicle usage types
        has_personal = any(o.usage_type == VehicleUsageType.PERSONAL for o in ownerships)
        has_motor = any(o.usage_type == VehicleUsageType.COMMERCIAL_MOTORCYCLE for o in ownerships)
        has_car = any(o.usage_type == VehicleUsageType.COMMERCIAL_CAR for o in ownerships)
        has_truck = any(o.usage_type == VehicleUsageType.COMMERCIAL_TRUCK for o in ownerships)

        base1 = warga_quota if has_personal else Decimal("0.00")
        base2 = motor_quota if has_motor else (car_quota if has_car else Decimal("0.00"))
        base3 = truck_quota if has_truck else Decimal("0.00")

        risk_index = int(profile.risk_score)
        modifier_val = max(Decimal("0.00"), Decimal("1.00") - (Decimal(risk_index) / Decimal("100.00")))
        final_quota = (base1 + base2 + base3) * modifier_val

        # Mask NIK
        nik = profile.nik_snapshot
        nik_sensor = f"{nik[:4]}********{nik[-4:]}" if len(nik) >= 8 else nik

        items.append(
            GovernmentQuotaTransactionItem(
                nikSensor=f"NIK {nik_sensor}",
                nama=profile.user.name,
                baseQuota1=f"{int(base1)} L",
                baseQuota2=f"{int(base2)} L",
                baseQuota3=f"{int(base3)} L",
                riskIndex=risk_index,
                modifier=f"{float(modifier_val):.1f}",
                finalQuota=f"{int(final_quota)} L"
            )
        )

    return {
        "items": items,
        "total": len(items)
    }


@router.get("/blacklist", response_model=BlacklistListResponse)
async def get_government_blacklist(
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    stmt = select(User).options(selectinload(User.buyer_profile)).filter(
        or_(
            User.is_blocked == True,
            User.frozen_until > datetime.utcnow()
        )
    )
    enforced_users = (await db.execute(stmt)).scalars().all()

    items = []
    for u in enforced_users:
        bp = u.buyer_profile
        nik = bp.nik_snapshot if bp else "—"
        plate = "—"
        vtype = "Tidak Ada Kendaraan"
        if bp:
            v_stmt = select(VehicleOwnership).filter(
                VehicleOwnership.owner_type == VehicleOwnerType.BUYER_PROFILE,
                VehicleOwnership.owner_id == bp.id
            ).limit(1)
            ownership = (await db.execute(v_stmt)).scalars().first()
            if ownership:
                plate = ownership.plate_number_snapshot
                # Fetch registry detail
                from app.modules.registries.models import VehicleRegistryMockup
                reg_stmt = select(VehicleRegistryMockup).filter(VehicleRegistryMockup.id == ownership.vehicle_id)
                reg = (await db.execute(reg_stmt)).scalars().first()
                if reg:
                    vtype = f"{reg.brand} {reg.vehicle_type} ({reg.engine_capacity_cc}cc)"

        status = "BLOCKED" if u.is_blocked else "FREEZE"
        reason = "Tindakan Keamanan Regulator"
        if bp:
            from app.modules.transactions.models import FraudLog
            f_stmt = select(FraudLog).filter(FraudLog.buyer_profile_id == bp.id).order_by(FraudLog.created_at.desc()).limit(1)
            f_log = (await db.execute(f_stmt)).scalars().first()
            if f_log and f_log.detected_frauds:
                reason = f_log.detected_frauds[0].get("reason", "Anomali terdeteksi")

        items.append(
            BlacklistItem(
                id=u.id,
                accountId=f"NIK {nik}",
                holderName=u.name,
                plate=plate,
                type=vtype,
                reason=reason,
                dateAdded=u.timestamp.strftime("%d %b %Y") if u.timestamp else "Hari Ini",
                officer="BPH Migas AI" if "AI" in reason or u.is_blocked else "Drs. Budi Santoso",
                status=status
            )
        )

    return {"items": items, "total": len(items)}


@router.post("/blacklist")
async def create_government_blacklist(
    request: BlacklistCreateRequest,
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    nik_val = request.accountId.replace("NIK ", "").strip()
    bp_stmt = select(BuyerProfile).options(selectinload(BuyerProfile.user)).filter(BuyerProfile.nik_snapshot == nik_val)
    bp = (await db.execute(bp_stmt)).scalars().first()
    if not bp or not bp.user:
        raise HTTPException(status_code=404, detail="Profil Buyer dengan NIK tersebut tidak ditemukan.")

    u = bp.user
    if request.status == "BLOCKED":
        u.is_blocked = True
        u.frozen_until = None
    else:  # FREEZE
        u.is_blocked = False
        u.frozen_until = datetime.utcnow() + timedelta(days=14)

    # Trigger mock fraud log update to store the reason if desired
    from app.modules.transactions.models import FraudLog, FraudRiskLevel, FraudActionTaken
    # Look up dynamic SPBU or default
    from app.modules.gas_stations.models import GasStation
    gs_stmt = select(GasStation.id).limit(1)
    gs_id = (await db.execute(gs_stmt)).scalar()
    if not gs_id:
        gs = GasStation(
            name="SPBU Temp",
            latitude=Decimal("-6.200000"),
            longitude=Decimal("106.800000"),
        )
        db.add(gs)
        await db.flush()
        gs_id = gs.id

    # Find vehicle ownership
    v_stmt = select(VehicleOwnership).filter(
        VehicleOwnership.owner_type == VehicleOwnerType.BUYER_PROFILE,
        VehicleOwnership.owner_id == bp.id
    ).limit(1)
    ownership = (await db.execute(v_stmt)).scalars().first()

    # Create dummy fraud log
    import random
    case_num = f"CF{random.randint(10000, 99999)}"
    f_log = FraudLog(
        case_id=case_num,
        buyer_profile_id=bp.id,
        gas_station_id=gs_id,
        vehicle_ownership_id=ownership.id if ownership else None,
        plate_number_snapshot=ownership.plate_number_snapshot if ownership else "-",
        nik_snapshot=bp.nik_snapshot,
        risk_score=95 if request.status == "BLOCKED" else 75,
        risk_level=FraudRiskLevel.CRITICAL if request.status == "BLOCKED" else FraudRiskLevel.HIGH_RISK,
        action_taken=FraudActionTaken.BLOCK_ACCOUNT if request.status == "BLOCKED" else FraudActionTaken.FREEZE_ACCOUNT,
        detected_frauds=[{"type": "MANUAL_ENFORCEMENT", "points": 100, "reason": request.reason}],
        status="RESOLVED",
        resolution_notes=request.reason,
        resolved_by_user_id=current_user.id,
        resolved_at=datetime.utcnow()
    )
    db.add(f_log)

    await db.commit()
    return {"message": "Success"}


@router.put("/blacklist/{user_id}/restore")
async def restore_government_blacklist(
    user_id: str,
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    stmt = select(User).filter(User.id == user_id)
    u = (await db.execute(stmt)).scalars().first()
    if not u:
        raise HTTPException(status_code=404, detail="User tidak ditemukan.")

    u.is_blocked = False
    u.frozen_until = None
    await db.commit()
    return {"message": "Success"}
