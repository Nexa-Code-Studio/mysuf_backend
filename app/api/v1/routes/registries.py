from typing import Any
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.modules.registries.schemas import (
    CitizenCreate,
    CitizenListResponse,
    CitizenResponse,
    CitizenUpdate,
    KKCreate,
    KKListResponse,
    KKResponse,
    KKUpdate,
    VehicleCreate,
    VehicleListResponse,
    VehicleResponse,
    VehicleUpdate,
)
from app.modules.registries.service import RegistryService

router = APIRouter()

# ====================================================
# KK (Kartu Keluarga) Endpoints
# ====================================================

@router.get("/kk", response_model=KKListResponse)
async def read_kks(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Retrieve Kartu Keluarga (KK) entries with pagination.
    """
    service = RegistryService(db)
    return await service.get_kks(page=page, page_size=page_size)


@router.get("/kk/{kk_id}", response_model=KKResponse)
async def read_kk(
    kk_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Retrieve a specific Kartu Keluarga (KK) by its UUID.
    """
    service = RegistryService(db)
    return await service.get_kk(kk_id)


@router.post("/kk", response_model=KKResponse, status_code=status.HTTP_201_CREATED)
async def create_kk(
    kk_in: KKCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Create a new Kartu Keluarga (KK).
    """
    service = RegistryService(db)
    return await service.create_kk(kk_in)


@router.put("/kk/{kk_id}", response_model=KKResponse)
async def update_kk(
    kk_id: str,
    kk_in: KKUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Update a Kartu Keluarga (KK).
    """
    service = RegistryService(db)
    return await service.update_kk(kk_id, kk_in)


@router.delete("/kk/{kk_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kk(
    kk_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a Kartu Keluarga (KK).
    """
    service = RegistryService(db)
    await service.delete_kk(kk_id)


# ====================================================
# Citizen Registry Mockup Endpoints
# ====================================================

@router.get("/citizens", response_model=CitizenListResponse)
async def read_citizens(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Retrieve citizen registry mockup entries with pagination.
    """
    service = RegistryService(db)
    return await service.get_citizens(page=page, page_size=page_size)


@router.get("/citizens/{citizen_id}", response_model=CitizenResponse)
async def read_citizen(
    citizen_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Retrieve a specific citizen registry entry by its UUID.
    """
    service = RegistryService(db)
    return await service.get_citizen(citizen_id)


@router.post("/citizens", response_model=CitizenResponse, status_code=status.HTTP_201_CREATED)
async def create_citizen(
    citizen_in: CitizenCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Create a new citizen registry entry.
    """
    service = RegistryService(db)
    return await service.create_citizen(citizen_in)


@router.put("/citizens/{citizen_id}", response_model=CitizenResponse)
async def update_citizen(
    citizen_id: str,
    citizen_in: CitizenUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Update a citizen registry entry.
    """
    service = RegistryService(db)
    return await service.update_citizen(citizen_id, citizen_in)


@router.delete("/citizens/{citizen_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_citizen(
    citizen_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a citizen registry entry.
    """
    service = RegistryService(db)
    await service.delete_citizen(citizen_id)


# ====================================================
# Vehicle Registry Mockup Endpoints
# ====================================================

@router.get("/vehicles", response_model=VehicleListResponse)
async def read_vehicles(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Retrieve vehicle registry mockup entries with pagination.
    """
    service = RegistryService(db)
    return await service.get_vehicles(page=page, page_size=page_size)


@router.get("/vehicles/{vehicle_id}", response_model=VehicleResponse)
async def read_vehicle(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Retrieve a specific vehicle registry entry by its UUID.
    """
    service = RegistryService(db)
    return await service.get_vehicle(vehicle_id)


@router.post("/vehicles", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
async def create_vehicle(
    vehicle_in: VehicleCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Create a new vehicle registry entry.
    """
    service = RegistryService(db)
    return await service.create_vehicle(vehicle_in)


@router.put("/vehicles/{vehicle_id}", response_model=VehicleResponse)
async def update_vehicle(
    vehicle_id: str,
    vehicle_in: VehicleUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Update a vehicle registry entry.
    """
    service = RegistryService(db)
    return await service.update_vehicle(vehicle_id, vehicle_in)


@router.delete("/vehicles/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vehicle(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a vehicle registry entry.
    """
    service = RegistryService(db)
    await service.delete_vehicle(vehicle_id)
