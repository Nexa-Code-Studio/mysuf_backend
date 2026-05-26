from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.modules.users.models import User, UserRole
from app.modules.transactions.service import TransactionService

router = APIRouter()


@router.get("/summary")
async def get_spbu_dashboard_summary(
    gas_station_id: UUID | None = Query(None, description="Gas station ID filter (only for Super/Gov admins)"),
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN, UserRole.SPBU_ADMIN, UserRole.SALES_OFFICER])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    service = TransactionService(db)
    return await service.get_spbu_dashboard_summary(
        current_user,
        gas_station_id=gas_station_id
    )


@router.get("/transactions")
async def get_spbu_transactions(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    fuel_type: str | None = Query(None, description="Filter by fuel type"),
    status: str | None = Query(None, description="Filter by status"),
    search: str | None = Query(None, description="Search plate, NIK, transaction ID, or cashier name"),
    gas_station_id: UUID | None = Query(None, description="Gas station ID filter (only for Super/Gov admins)"),
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN, UserRole.SPBU_ADMIN, UserRole.SALES_OFFICER])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    service = TransactionService(db)
    return await service.get_spbu_transactions(
        current_user,
        page=page,
        size=size,
        fuel_type=fuel_type,
        status=status,
        search=search,
        gas_station_id=gas_station_id
    )


# ----------------------------------------------------
# SPBU Staff CRUD Routes
# ----------------------------------------------------
from sqlalchemy.future import select
from sqlalchemy import or_
from app.modules.users.schemas import UserCreate, UserUpdate, UserResponse
from app.modules.users.service import UserService

@router.get("/staff", response_model=list[UserResponse])
async def list_spbu_staff(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    search: str | None = Query(None, description="Search by name or email"),
    shift: str | None = Query(None, description="Filter by shift"),
    role: str | None = Query(None, description="Filter by role: Admin or Cashier"),
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.SPBU_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    stmt = select(User)
    
    # If user is SPBU_ADMIN, restrict to their gas station and SPBU_ADMIN / SALES_OFFICER roles
    if UserRole.SPBU_ADMIN in current_user.role:
        if not current_user.gas_station_id:
            raise HTTPException(status_code=400, detail="Admin is not assigned to any gas station")
        stmt = stmt.filter(User.gas_station_id == current_user.gas_station_id)
        stmt = stmt.filter(
            or_(
                User.role.any(UserRole.SPBU_ADMIN),
                User.role.any(UserRole.SALES_OFFICER)
            )
        )
    else:
        # SUPER_ADMIN / GOV_ADMIN can list all SPBU staff roles
        stmt = stmt.filter(
            or_(
                User.role.any(UserRole.SPBU_ADMIN),
                User.role.any(UserRole.SALES_OFFICER)
            )
        )
        
    if search:
        stmt = stmt.filter(
            or_(
                User.name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )
        
    if shift:
        stmt = stmt.filter(User.shift.ilike(f"%{shift}%"))
        
    if role:
        if role.lower() == "admin":
            stmt = stmt.filter(User.role.any(UserRole.SPBU_ADMIN))
        elif role.lower() == "cashier":
            stmt = stmt.filter(User.role.any(UserRole.SALES_OFFICER))

    stmt = stmt.offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/staff", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_spbu_staff(
    staff_in: UserCreate,
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.SPBU_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    if UserRole.SPBU_ADMIN in current_user.role:
        if not current_user.gas_station_id:
            raise HTTPException(status_code=400, detail="Admin is not assigned to any gas station")
        staff_in.gas_station_id = current_user.gas_station_id
        
        for r in staff_in.role:
            if r not in [UserRole.SPBU_ADMIN, UserRole.SALES_OFFICER]:
                raise HTTPException(status_code=403, detail="Can only create SPBU Admin or Cashier")
                
    service = UserService(db)
    return await service.create_user(user_in=staff_in, current_user=current_user)


@router.put("/staff/{staff_id}", response_model=UserResponse)
async def update_spbu_staff(
    staff_id: UUID,
    staff_in: UserUpdate,
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.SPBU_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    service = UserService(db)
    staff = await service.get_user(str(staff_id))
    
    if UserRole.SPBU_ADMIN in current_user.role:
        if not current_user.gas_station_id:
            raise HTTPException(status_code=400, detail="Admin is not assigned to any gas station")
        if staff.gas_station_id != current_user.gas_station_id:
            raise HTTPException(status_code=403, detail="Not permitted to update staff of another gas station")
            
        if staff_in.role is not None:
            for r in staff_in.role:
                if r not in [UserRole.SPBU_ADMIN, UserRole.SALES_OFFICER]:
                    raise HTTPException(status_code=403, detail="Can only assign SPBU Admin or Cashier role")
                    
    return await service.update_user(user_id=str(staff_id), user_in=staff_in, current_user=current_user)


@router.delete("/staff/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_spbu_staff(
    staff_id: UUID,
    current_user: User = Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.SPBU_ADMIN])),
    db: AsyncSession = Depends(get_db)
) -> None:
    service = UserService(db)
    staff = await service.get_user(str(staff_id))
    
    if UserRole.SPBU_ADMIN in current_user.role:
        if not current_user.gas_station_id:
            raise HTTPException(status_code=400, detail="Admin is not assigned to any gas station")
        if staff.gas_station_id != current_user.gas_station_id:
            raise HTTPException(status_code=403, detail="Not permitted to delete staff of another gas station")
            
    await db.delete(staff)
    await db.commit()
    return None


