import math
from datetime import datetime
from decimal import Decimal
from typing import Any, List
from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.modules.subsidies.service import SubsidyService
from app.modules.subsidies.models import EligibilityStatus
from app.modules.transactions.models import FuelTransaction, TransactionFlow, TransactionType, WalletTransaction
from app.modules.users.schemas import UserCreate, UserUpdate, BuyerProfileCreate, BuyerProfileUpdate
from app.modules.users.models import User, UserRole, BuyerProfile, VerificationStatus
from app.modules.users.repository import UserRepository
from app.modules.vehicles.models import VehicleUsageType
from app.modules.auth.utils import has_role

class UserService:
    def __init__(self, db: AsyncSession):
        self.repo = UserRepository(db)
        self.subsidy_service = SubsidyService(db)

    async def get_users(self, page: int = 1, page_size: int = 20) -> dict:
        skip = (page - 1) * page_size
        limit = page_size
        
        users = await self.repo.get_users(skip=skip, limit=limit)
        total = await self.repo.count_users()
        
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        
        return {
            "items": users,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages
            }
        }

    async def get_user(self, user_id: str) -> User:
        user = await self.repo.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user

    async def create_user(self, user_in: UserCreate, current_user: User | None = None) -> User:
        # Check if email exists
        existing_user = await self.repo.get_user_by_email(user_in.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The user with this email already exists in the system.",
            )

        # RBAC checks
        if current_user is None:
            # Public registration - only BUYER allowed, no gas_station/company association
            if set(user_in.role) != {UserRole.BUYER}:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Public registration can only create BUYER accounts")
            user_in.company_id = None
            user_in.gas_station_id = None
        else:
            if has_role(current_user, UserRole.SUPER_ADMIN):
                pass # Can create any role
            elif has_role(current_user, UserRole.SPBU_ADMIN):
                if UserRole.SALES_OFFICER not in user_in.role:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Gas Station Admin can only create SALES_OFFICER accounts")
                # Force link to their gas station
                user_in.gas_station_id = current_user.gas_station_id
                user_in.company_id = None
            elif has_role(current_user, UserRole.COMPANY_ADMIN):
                if UserRole.BUYER not in user_in.role:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Company Admin can only create BUYER accounts")
                # Force link to their company
                user_in.company_id = current_user.company_id
                user_in.gas_station_id = None
            else:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough privileges to create users")

        db_user = User(
            email=user_in.email,
            name=user_in.name,
            password=get_password_hash(user_in.password),
            role=user_in.role,
            is_active=user_in.is_active,
            employee_id=user_in.employee_id,
            gas_station_id=user_in.gas_station_id,
            company_id=user_in.company_id,
            shift=user_in.shift
        )
        return await self.repo.create_user(db_user)

    async def update_user(self, user_id: str, user_in: UserUpdate, current_user: User) -> User:
        user = await self.get_user(user_id)

        # RBAC checks
        is_superuser = has_role(current_user, UserRole.SUPER_ADMIN)
        is_self = str(current_user.id) == user_id
        is_gas_station_admin = has_role(current_user, UserRole.SPBU_ADMIN)
        
        if not (is_superuser or is_self or is_gas_station_admin):
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough privileges to edit this user")

        if is_gas_station_admin and not is_superuser:
            # If the user belongs to the admin's gas station, allow editing
            if user.gas_station_id == current_user.gas_station_id:
                pass
            else:
                # "Admin gas station bisa link akun buyer agar menjadi sales_officer"
                # They can only modify a BUYER, add SALES_OFFICER, and set gas_station_id
                if UserRole.BUYER not in user.role:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Gas Station Admin can only modify BUYER accounts")
                
                # Ensure they are only adding SALES_OFFICER and linking to their station
                if user_in.role is not None and UserRole.SALES_OFFICER in user_in.role:
                    user_in.gas_station_id = current_user.gas_station_id
                else:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Gas Station Admin can only grant SALES_OFFICER role")

        # Prevent normal users from escalating roles
        if not is_superuser and not is_gas_station_admin and user_in.role is not None:
             raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough privileges to modify roles")

        update_data = user_in.model_dump(exclude_unset=True)
        if "password" in update_data:
            update_data["password"] = get_password_hash(update_data["password"])
            
        for field, value in update_data.items():
            setattr(user, field, value)

        return await self.repo.update_user(user)

    async def delete_user(self, user_id: str, current_user: User) -> None:
        if not has_role(current_user, UserRole.SUPER_ADMIN):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only superadmin can delete users")
            
        user = await self.get_user(user_id)
        await self.repo.delete_user(user)

    async def create_buyer_profile(self, user_id: str, profile_in: BuyerProfileCreate) -> BuyerProfile:
        # Validate User exists and is BUYER
        user = await self.get_user(user_id)
        if UserRole.BUYER not in user.role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only users with BUYER role can have a buyer profile."
            )

        # Check for duplicate
        existing = await self.repo.get_buyer_profile_by_user_id(user_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Buyer profile already exists for this user."
            )

        # Validate kk_id exists
        kk = await self.repo.get_kk_by_id(str(profile_in.kk_id))
        if not kk:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The provided KK ID does not exist."
            )

        profile = BuyerProfile(
            nik_snapshot=profile_in.nik_snapshot,
            ktp_nfc_id_snapshot=profile_in.ktp_nfc_id_snapshot,
            kk_id=profile_in.kk_id,
            user_id=UUID(user_id) if isinstance(user_id, str) else user_id,
            verification_status=VerificationStatus.UNVERIFIED
        )
        return await self.repo.create_buyer_profile(profile)

    async def update_buyer_profile(self, user_id: str, profile_in: BuyerProfileUpdate) -> BuyerProfile:
        profile = await self.repo.get_buyer_profile_by_user_id(user_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Buyer profile not found."
            )

        # Validate kk_id if updated
        if profile_in.kk_id is not None:
            kk = await self.repo.get_kk_by_id(str(profile_in.kk_id))
            if not kk:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The provided KK ID does not exist."
                )

        update_data = profile_in.model_dump(exclude_unset=True)
        next_nfc_snapshot = update_data.get("ktp_nfc_id_snapshot")
        if next_nfc_snapshot is not None:
            next_nfc_snapshot = next_nfc_snapshot.strip()
            if not next_nfc_snapshot:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="NFC E-KTP tidak boleh kosong.",
                )
            if next_nfc_snapshot == profile.ktp_nfc_id_snapshot:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="NFC yang dipindai sama dengan NFC saat ini.",
                )

            existing_profile = await self.repo.get_buyer_profile_by_ktp_nfc_id_snapshot(next_nfc_snapshot)
            if existing_profile and existing_profile.id != profile.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="NFC E-KTP tersebut sudah digunakan oleh pengguna lain.",
                )
            update_data["ktp_nfc_id_snapshot"] = next_nfc_snapshot

        for field, value in update_data.items():
            setattr(profile, field, value)

        if next_nfc_snapshot is not None:
            ownerships = await self.repo.get_vehicle_ownerships_by_buyer_profile_id(profile.id)
            for ownership in ownerships:
                ownership.ktp_nfc_id_snapshot = next_nfc_snapshot

            requests = await self.repo.get_vehicle_ownership_requests_by_buyer_profile_id(profile.id)
            for request in requests:
                request.ktp_nfc_id_snapshot = next_nfc_snapshot

        return await self.repo.update_buyer_profile(profile)

    async def get_buyer_profile(self, user_id: str) -> BuyerProfile:
        profile = await self.repo.get_buyer_profile_by_user_id(user_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Buyer profile not found."
            )
        return profile

    async def check_buyer_profile(self, user_id: str) -> dict:
        profile = await self.repo.get_buyer_profile_by_user_id(user_id)
        if profile:
            return {
                "has_buyer_profile": True,
                "buyer_profile_id": profile.id,
                "verification_status": profile.verification_status.value
            }
        return {
            "has_buyer_profile": False,
            "buyer_profile_id": None,
            "verification_status": None
        }

    async def get_buyer_home(self, user_id: str, latitude: float | None, longitude: float | None) -> dict:
        buyer_profile = await self.repo.get_buyer_profile_by_user_id(user_id)
        if not buyer_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Buyer profile not found.",
            )

        from app.modules.vehicles.models import VehicleUsageType
        ownerships = await self.repo.get_vehicle_ownerships_by_ktp_nfc_id_snapshot(buyer_profile.ktp_nfc_id_snapshot)
        has_verified_vehicle = any(
            ownership.usage_type == VehicleUsageType.PERSONAL
            for ownership in ownerships
        )

        current_time = datetime.utcnow()
        personal_quota = await self._build_personal_quota_payload(
            buyer_profile=buyer_profile,
            month=current_time.month,
            year=current_time.year,
        )

        recent_transactions = await self._build_recent_transactions(buyer_profile)

        payload = {
            "vehicle_verification": {
                "has_verified_vehicle": has_verified_vehicle,
                "show_verify_vehicle_cta": not has_verified_vehicle,
                "cta_route": "/vehicles/add",
            },
            "personal_quota": personal_quota,
            "nearby_gas_stations": self._build_nearby_gas_stations(latitude, longitude),
            "recent_transactions": recent_transactions,
            "risk_status": {
                "verification_status": buyer_profile.verification_status,
                "risk_score": float(Decimal(buyer_profile.risk_score)),
            },
        }
        payload["nearby_gas_stations"] = await self.get_nearby_gas_stations(
            latitude=latitude,
            longitude=longitude,
            limit=3,
        )
        return payload

    async def get_nearby_gas_stations(
        self,
        latitude: float | None,
        longitude: float | None,
        limit: int = 10,
    ) -> dict:
        payload = self._build_nearby_gas_stations(latitude, longitude)
        if latitude is None or longitude is None:
            return payload

        gas_stations = await self.repo.list_gas_stations()
        items = []
        for gas_station in gas_stations:
            distance_km = self._calculate_distance_km(latitude, longitude, gas_station.latitude, gas_station.longitude)
            items.append(
                {
                    "id": gas_station.id,
                    "name": gas_station.name,
                    "latitude": float(gas_station.latitude),
                    "longitude": float(gas_station.longitude),
                    "distance_km": round(distance_km, 2),
                }
            )

        items.sort(key=lambda item: item["distance_km"])
        payload["items"] = items[:limit]
        return payload

    async def _build_recent_transactions(self, buyer_profile: BuyerProfile) -> list[dict]:
        wallet = await self.repo.get_wallet_by_owner_user_id(str(buyer_profile.user_id))
        wallet_transactions = await self.repo.get_recent_wallet_transactions(wallet.id, limit=10) if wallet else []
        fuel_transactions = await self.repo.get_recent_fuel_transactions(buyer_profile.id, limit=10)

        items: list[dict] = []
        fuel_wallet_transaction_ids = {
            str(fuel_transaction.wallet_transaction_id)
            for fuel_transaction in fuel_transactions
            if fuel_transaction.wallet_transaction_id is not None
        }

        for fuel_transaction in fuel_transactions:
            items.append(self._serialize_fuel_transaction_for_home(fuel_transaction))

        for wallet_transaction in wallet_transactions:
            if str(wallet_transaction.id) in fuel_wallet_transaction_ids:
                continue
            serialized = self._serialize_wallet_transaction_for_home(wallet_transaction)
            if serialized is not None:
                items.append(serialized)

        items.sort(key=lambda item: item["occurred_at"], reverse=True)
        return items[:3]

    def _serialize_fuel_transaction_for_home(self, fuel_transaction: FuelTransaction) -> dict:
        fuel_type_name = fuel_transaction.fuel_type.name if fuel_transaction.fuel_type else "Bahan Bakar"
        gas_station_name = fuel_transaction.gas_station.name if fuel_transaction.gas_station else "SPBU"
        occurred_at = fuel_transaction.created_at
        return {
            "id": str(fuel_transaction.id),
            "tile_type": "FUEL",
            "title": f"{fuel_type_name} - {gas_station_name}",
            "subtitle": self._format_home_datetime(occurred_at),
            "amount": float(Decimal(fuel_transaction.total_amount)),
            "transaction_flow": TransactionFlow.OUT.value,
            "status": fuel_transaction.transaction_status.value,
            "occurred_at": occurred_at,
            "fuel": {
                "fuel_type_name": fuel_type_name,
                "gas_station_name": gas_station_name,
                "liters": float(Decimal(fuel_transaction.liters)),
            },
        }

    def _serialize_wallet_transaction_for_home(self, wallet_transaction: WalletTransaction) -> dict | None:
        normalized_type = self._normalize_wallet_transaction_type(wallet_transaction)
        if normalized_type == TransactionType.TOP_UP:
            title = "Top Up Saldo"
            tile_type = "TOP_UP"
        elif normalized_type == TransactionType.TRANSFER:
            title = "Transfer Saldo"
            tile_type = "TRANSFER"
        else:
            return None

        return {
            "id": str(wallet_transaction.id),
            "tile_type": tile_type,
            "title": title,
            "subtitle": self._format_home_datetime(wallet_transaction.created_at),
            "amount": float(Decimal(wallet_transaction.amount)),
            "transaction_flow": wallet_transaction.transaction_flow.value,
            "status": wallet_transaction.status.value,
            "occurred_at": wallet_transaction.created_at,
            "fuel": None,
        }

    def _normalize_wallet_transaction_type(self, wallet_transaction: WalletTransaction) -> TransactionType:
        if wallet_transaction.fuel_transactions:
            return TransactionType.FUEL_PURCHASE
        return wallet_transaction.type

    def _build_nearby_gas_stations(self, latitude: float | None, longitude: float | None) -> dict:
        if latitude is None or longitude is None:
            return {
                "location_available": False,
                "message": "Lokasi Anda tidak ditemukan, tolong nyalakan GPS.",
                "items": [],
            }
        return {
            "location_available": True,
            "message": None,
            "items": [],
        }

    def _format_home_datetime(self, value: datetime) -> str:
        month_names = [
            "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
            "Jul", "Agu", "Sep", "Okt", "Nov", "Des",
        ]
        return f"{value.day:02d} {month_names[value.month - 1]} {value.year}, {value.hour:02d}:{value.minute:02d}"

    def _calculate_distance_km(self, latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
        earth_radius_km = 6371.0
        lat_a = math.radians(latitude_a)
        lon_a = math.radians(longitude_a)
        lat_b = math.radians(latitude_b)
        lon_b = math.radians(longitude_b)
        delta_lat = lat_b - lat_a
        delta_lon = lon_b - lon_a

        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return earth_radius_km * c

    async def _get_latest_personal_eligibility(self, buyer_profile: BuyerProfile):
        policy = await self.subsidy_service.repo.get_subsidy_policy_by_usage_type(
            VehicleUsageType.PERSONAL
        )
        if policy is None:
            return None

        return await self.subsidy_service.repo.get_latest_kk_subsidy_eligibility(
            kk_id=buyer_profile.kk_id,
            subsidy_policy_id=policy.id,
        )

    async def _build_personal_quota_payload(
        self,
        buyer_profile: BuyerProfile,
        month: int,
        year: int,
    ) -> dict[str, float | int] | None:
        latest_eligibility = await self._get_latest_personal_eligibility(buyer_profile)
        if latest_eligibility is not None and latest_eligibility.eligibility_status != EligibilityStatus.ELIGIBLE:
            return None

        quota = await self.subsidy_service.get_or_sync_personal_quota(
            buyer_profile=buyer_profile,
            month=month,
            year=year,
        )
        if quota is None or not quota.is_active:
            return None

        quota_liters = float(Decimal(quota.quota_liters))
        used_liters = float(Decimal(quota.used_liters))
        remaining_liters = max(quota_liters - used_liters, 0.0)
        return {
            "month": month,
            "year": year,
            "quota_liters": quota_liters,
            "used_liters": used_liters,
            "remaining_liters": remaining_liters,
        }

    async def get_user_profile_detail(self, user_id: str) -> dict:
        from sqlalchemy import select, func
        from sqlalchemy.orm import selectinload
        from app.modules.users.models import BuyerProfile, VerificationStatus
        from app.modules.registries.models import KK
        from app.modules.wallets.models import Wallet, OwnerType
        from app.modules.vehicles.models import VehicleOwnership, VehicleOwnerType
        from app.modules.subsidies.models import KKSubsidyEligibility, EligibilityStatus, SubsidyQuota, SubsidyOwnerType
        from datetime import datetime

        user = await self.repo.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        db = self.repo.db

        # Fetch Wallet
        wallet_result = await db.execute(
            select(Wallet).filter(Wallet.owner_id == user.id, Wallet.owner_type == OwnerType.USER)
        )
        wallet = wallet_result.scalars().first()
        wallet_balance = int(wallet.balance) if wallet else 0

        # Default values if no buyer profile exists
        nik_masked = ""
        is_verified = False
        is_eligible = False
        family_card_number = ""
        vehicles_count = 0
        quota_remaining = 0
        is_pin_active = False
        pekerjaan = "LAINNYA"
        penghasilan = 0.0

        # Fetch BuyerProfile
        profile_result = await db.execute(
            select(BuyerProfile)
            .options(selectinload(BuyerProfile.kk))
            .filter(BuyerProfile.user_id == user.id)
        )
        buyer_profile = profile_result.scalars().first()

        if buyer_profile:
            is_pin_active = buyer_profile.is_pin_active
            # nikMasked
            nik = buyer_profile.nik_snapshot
            if len(nik) >= 8:
                nik_masked = f"{nik[:4]}****{nik[-4:]}"
            else:
                nik_masked = nik

            # isVerified
            is_verified = buyer_profile.verification_status == VerificationStatus.VERIFIED

            # familyCardNumber
            if buyer_profile.kk:
                family_card_number = buyer_profile.kk.code

            # vehiclesCount
            vehicles_count = 0

            # quotaRemaining & isEligible
            now = datetime.utcnow()
            quota_result = await db.execute(
                select(SubsidyQuota)
                .filter(
                    SubsidyQuota.owner_type == SubsidyOwnerType.BUYER_PROFILE,
                    SubsidyQuota.owner_id == buyer_profile.id,
                    SubsidyQuota.month == now.month,
                    SubsidyQuota.year == now.year
                )
            )
            quota = quota_result.scalars().first()
            if quota is None:
                quota = await self.subsidy_service.get_or_sync_personal_quota(
                    buyer_profile=buyer_profile,
                    month=now.month,
                    year=now.year,
                )
            is_eligible = quota.is_active if quota else False
            quota_remaining = int(quota.quota_liters - quota.used_liters) if quota else 0

            # Query Citizen details for job and income
            from app.modules.registries.models import CitizenRegistryMockup
            stmt_citizen = select(CitizenRegistryMockup).filter(CitizenRegistryMockup.nik == buyer_profile.nik_snapshot)
            citizen = (await db.execute(stmt_citizen)).scalars().first()
            pekerjaan = citizen.pekerjaan if citizen else "LAINNYA"
            penghasilan = float(citizen.penghasilan) if citizen and citizen.penghasilan else 0.0

        return {
            "name": user.name,
            "nikMasked": nik_masked,
            "isVerified": is_verified,
            "isEligible": is_eligible,
            "familyCardNumber": family_card_number,
            "vehiclesCount": vehicles_count,
            "quotaRemaining": quota_remaining,
            "walletBalance": wallet_balance,
            "isPinActive": is_pin_active,
            "pekerjaan": pekerjaan,
            "penghasilan": penghasilan
        }

    async def get_buyer_quota_detail(self, user_id: str) -> dict:
        buyer_profile = await self.repo.get_buyer_profile_by_user_id(user_id)
        if not buyer_profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Buyer profile not found.",
            )

        current_time = datetime.utcnow()
        personal_quota = await self._build_personal_quota_payload(
            buyer_profile=buyer_profile,
            month=current_time.month,
            year=current_time.year,
        )

        # Local imports to prevent circular references
        from app.modules.fuels.models import FuelType, SubsidyType
        from app.modules.vehicles.models import VehicleOwnership
        from app.modules.registries.models import VehicleRegistryMockup
        from app.modules.transactions.models import FuelTransaction, FuelTransactionStatus
        from sqlalchemy import select, func

        # 1. Fetch subsidized fuel types
        fuels_result = await self.repo.db.execute(
            select(FuelType).filter(FuelType.subsidy_type == SubsidyType.SUBSIDIZED)
        )
        subsidized_fuels = [
            {
                "id": fuel.id,
                "name": fuel.name,
                "price_per_liter": float(Decimal(fuel.price_per_liter)),
                "subsidy_price_per_liter": float(Decimal(fuel.subsidy_price_per_liter)) if fuel.subsidy_price_per_liter is not None else None,
            }
            for fuel in fuels_result.scalars().all()
        ]

        # 2. Fetch vehicles and total purchase liters
        vehicles_query = (
            select(VehicleOwnership, VehicleRegistryMockup.brand)
            .join(VehicleRegistryMockup, VehicleOwnership.vehicle_id == VehicleRegistryMockup.id)
            .filter(VehicleOwnership.ktp_nfc_id_snapshot == buyer_profile.ktp_nfc_id_snapshot)
        )
        vehicles_result = await self.repo.db.execute(vehicles_query)

        vehicles_list = []
        for ownership, brand in vehicles_result.all():
            liters_query = (
                select(func.coalesce(func.sum(FuelTransaction.liters), 0))
                .filter(
                    FuelTransaction.vehicle_ownership_id == ownership.id,
                    FuelTransaction.transaction_status == FuelTransactionStatus.COMPLETED
                )
            )
            liters_result = await self.repo.db.execute(liters_query)
            total_liters = float(Decimal(liters_result.scalar()))

            vehicles_list.append({
                "id": ownership.id,
                "plate_number": ownership.plate_number_snapshot,
                "brand": brand,
                "total_liters_purchased": total_liters
            })

        return {
            "personal_quota": personal_quota,
            "subsidized_fuels": subsidized_fuels,
            "vehicles": vehicles_list
        }

    async def update_buyer_pin(self, user_id: str, pin_in: Any) -> dict:
        from app.core.security import get_password_hash, verify_password
        
        if not pin_in.pin.isdigit() or len(pin_in.pin) != 6:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PIN harus berupa 6 digit angka."
            )
            
        profile = await self.repo.get_buyer_profile_by_user_id(user_id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profil buyer tidak ditemukan."
            )
            
        if profile.is_pin_active:
            if not pin_in.old_pin:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="PIN lama harus dimasukkan."
                )
            if not verify_password(pin_in.old_pin, profile.pin_hash):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="PIN lama salah."
                )
                
        profile.pin_hash = get_password_hash(pin_in.pin)
        profile.is_pin_active = True
        
        await self.repo.update_buyer_profile(profile)
        return {"message": "PIN berhasil disimpan."}


    async def update_device_token(self, user_id: str, token: str) -> dict:
        """
        Updates the authenticated user's FCM device token.
        """
        user = await self.repo.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User tidak ditemukan."
            )
        user.fcm_token = token
        await self.repo.db.commit()
        await self.repo.db.refresh(user)
        return {"message": "Token perangkat berhasil didaftarkan."}

    @staticmethod
    def update_user_fraud_status(user: User, risk_score: float) -> None:
        """
        Updates the user's is_blocked and frozen_until fields dynamically
        based on the risk score classification tiers.
        """
        from datetime import datetime, timedelta
        if risk_score > 100:
            user.is_blocked = True
            user.frozen_until = None
        elif risk_score >= 61:
            user.is_blocked = False
            # Smart calculation of frozen duration
            if risk_score >= 91:
                user.frozen_until = datetime.utcnow() + timedelta(days=14)
            elif risk_score >= 81:
                user.frozen_until = datetime.utcnow() + timedelta(days=7)
            elif risk_score >= 71:
                user.frozen_until = datetime.utcnow() + timedelta(days=3)
            else:
                user.frozen_until = datetime.utcnow() + timedelta(days=1)
        else:
            user.is_blocked = False
            user.frozen_until = None

    @staticmethod
    def check_user_fraud_status(user: User) -> None:
        """
        Raises an HTTP exception if the user is blocked or frozen.
        """
        from datetime import datetime
        if getattr(user, "is_blocked", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Akun Anda diblokir secara permanen oleh sistem keamanan karena skor risiko kritis."
            )
        
        frozen_until = getattr(user, "frozen_until", None)
        if frozen_until and frozen_until > datetime.utcnow():
            remaining = frozen_until - datetime.utcnow()
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Akun Anda dibekukan sementara hingga {frozen_until.strftime('%Y-%m-%d %H:%M:%S')} UTC. Tersisa {hours} jam {minutes} menit."
            )

