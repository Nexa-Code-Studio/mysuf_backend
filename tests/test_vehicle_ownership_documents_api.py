import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.main import app
from app.modules.vehicles.models import VehicleOwnership, VehicleOwnershipDocument
from app.modules.vehicles.service import VehicleService


@pytest.mark.anyio
async def test_create_vehicle_ownership_with_documents_stores_files_and_metadata():
    ownership_id = None
    storage_dir: Path | None = None

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.post(
                "/api/v1/vehicle-ownerships/",
                data={
                    "owner_type": "BUYER_PROFILE",
                    "owner_id": str(uuid4()),
                    "vehicle_id": str(uuid4()),
                    "ownership_status": "PERSONAL",
                    "usage_type": "OJOL",
                    "quota_mode": "DEDICATED_VEHICLE_QUOTA",
                    "plate_number_snapshot": "B 1234 TEST",
                    "ktp_nfc_id_snapshot": "NFC-TEST-1234",
                },
                files={
                    "stnk_photo": ("stnk.jpg", b"fake-stnk-image", "image/jpeg"),
                    "vehicle_photo": ("vehicle.jpg", b"fake-vehicle-image", "image/jpeg"),
                    "productive_business_proof": ("proof.pdf", b"fake-proof-pdf", "application/pdf"),
                },
            )

        assert res.status_code == 201
        body = res.json()
        ownership_id = body["id"]
        assert body["usage_type"] == "OJOL"
        assert body["quota_mode"] == "DEDICATED_VEHICLE_QUOTA"
        assert len(body["documents"]) == 3

        storage_dir = VehicleService.STORAGE_ROOT / ownership_id
        assert storage_dir.exists()
        assert (storage_dir / "stnk-photo.jpg").exists()
        assert (storage_dir / "vehicle-photo.jpg").exists()
        assert (storage_dir / "productive-business-proof.pdf").exists()
    finally:
        async with AsyncSessionLocal() as session:
            if ownership_id is not None:
                await session.execute(
                    delete(VehicleOwnershipDocument).where(
                        VehicleOwnershipDocument.vehicle_ownership_id == ownership_id
                    )
                )
                await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id == ownership_id))
                await session.commit()

        if storage_dir and storage_dir.exists():
            shutil.rmtree(storage_dir, ignore_errors=True)


@pytest.mark.anyio
async def test_create_vehicle_ownership_requires_productive_business_proof_for_ojol_and_umkm():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/api/v1/vehicle-ownerships/",
            data={
                "owner_type": "BUYER_PROFILE",
                "owner_id": str(uuid4()),
                "vehicle_id": str(uuid4()),
                "ownership_status": "PERSONAL",
                "usage_type": "OJOL",
                "quota_mode": "DEDICATED_VEHICLE_QUOTA",
                "plate_number_snapshot": "B 9999 TEST",
                "ktp_nfc_id_snapshot": "NFC-TEST-9999",
            },
            files={
                "stnk_photo": ("stnk.jpg", b"fake-stnk-image", "image/jpeg"),
                "vehicle_photo": ("vehicle.jpg", b"fake-vehicle-image", "image/jpeg"),
            },
        )

    assert res.status_code == 400
    assert res.json()["detail"] == "Productive business proof is required for OJOL and UMKM vehicles."
