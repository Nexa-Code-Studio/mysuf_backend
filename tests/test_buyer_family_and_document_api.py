import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.modules.registries.models import CitizenRegistryMockup, KK, VehicleRegistryMockup
from app.modules.subsidies.models import KKSubsidyEligibility
from app.modules.users.models import BuyerProfile, User, UserRole, VerificationStatus
from app.modules.vehicles.models import (
    VehicleOwnership,
    VehicleOwnershipDocument,
    VehicleOwnershipDocumentType,
    VehicleOwnershipRequest,
    VehicleOwnershipRequestDocument,
    VehicleOwnershipRequestStatus,
    VehicleOwnerType,
    VehicleOwnershipStatus,
    VehicleQuotaMode,
    VehicleUsageType,
)
from app.modules.vehicles.service import VehicleService


def _build_buyer_token(user_id: str) -> str:
    return create_access_token(
        subject=user_id,
        session_id=str(uuid4()),
        client_type="BUYER_ANDROID",
        roles=[UserRole.BUYER.value],
        allowed_apps=["BUYER_ANDROID"],
    )


@pytest.mark.anyio
async def test_buyer_family_overview_pending_list_and_document_streams():
    shared_vehicle_storage_dir: Path | None = None
    request_storage_dir: Path | None = None
    ids: dict[str, object] = {}

    try:
        async with AsyncSessionLocal() as session:
            kk = KK(code=f"KK-FAMILY-{uuid4().hex[:8]}")
            user_a = User(
                name="Budi Santoso",
                email=f"budi-{uuid4().hex[:8]}@example.com",
                password=get_password_hash("secret123"),
                role=[UserRole.BUYER],
                is_active=True,
            )
            user_b = User(
                name="Siti Rahma",
                email=f"siti-{uuid4().hex[:8]}@example.com",
                password=get_password_hash("secret123"),
                role=[UserRole.BUYER],
                is_active=True,
            )
            buyer_profile_a = BuyerProfile(
                nik_snapshot=f"3171{uuid4().hex[:12]}",
                ktp_nfc_id_snapshot=f"NFC-{uuid4().hex[:8]}",
                kk=kk,
                user=user_a,
                verification_status=VerificationStatus.VERIFIED,
            )
            buyer_profile_b = BuyerProfile(
                nik_snapshot=f"3171{uuid4().hex[:12]}",
                ktp_nfc_id_snapshot=f"NFC-{uuid4().hex[:8]}",
                kk=kk,
                user=user_b,
                verification_status=VerificationStatus.VERIFIED,
            )
            citizen_a = CitizenRegistryMockup(
                nik=buyer_profile_a.nik_snapshot,
                nama="Budi Santoso",
                ktp_nfc_id=buyer_profile_a.ktp_nfc_id_snapshot,
                kk=kk,
            )
            citizen_b = CitizenRegistryMockup(
                nik=buyer_profile_b.nik_snapshot,
                nama="Siti Rahma",
                ktp_nfc_id=buyer_profile_b.ktp_nfc_id_snapshot,
                kk=kk,
            )
            citizen_c = CitizenRegistryMockup(
                nik=f"3171{uuid4().hex[:12]}",
                nama="Dimas Santoso",
                ktp_nfc_id=f"NFC-{uuid4().hex[:8]}",
                kk=kk,
            )
            shared_registry_vehicle = VehicleRegistryMockup(
                plate_number="B 3333 FAM",
                registration_number=f"STNK-FAM-{uuid4().hex[:8]}",
                brand="Toyota",
                vehicle_type="Avanza",
                manufacture_year=2021,
                color="Hitam",
                engine_capacity_cc=1496,
                pkb="500000.00",
                njkb="190000000.00",
                owner_name="Budi Santoso",
                owner_nik=buyer_profile_a.nik_snapshot,
            )
            pending_registry_vehicle = VehicleRegistryMockup(
                plate_number="B 4444 FAM",
                registration_number=f"STNK-PEND-{uuid4().hex[:8]}",
                brand="Yamaha",
                vehicle_type="NMAX",
                manufacture_year=2022,
                color="Merah",
                engine_capacity_cc=155,
                pkb="650000.00",
                njkb="32000000.00",
                owner_name="Siti Rahma",
                owner_nik=buyer_profile_b.nik_snapshot,
            )

            session.add_all([
                kk,
                user_a,
                user_b,
                buyer_profile_a,
                buyer_profile_b,
                citizen_a,
                citizen_b,
                citizen_c,
                shared_registry_vehicle,
                pending_registry_vehicle,
            ])
            await session.commit()
            await session.refresh(user_a)
            await session.refresh(buyer_profile_a)
            await session.refresh(buyer_profile_b)
            await session.refresh(shared_registry_vehicle)
            await session.refresh(pending_registry_vehicle)

            ownership_a = VehicleOwnership(
                owner_type=VehicleOwnerType.BUYER_PROFILE,
                owner_id=buyer_profile_a.id,
                vehicle_id=shared_registry_vehicle.id,
                ownership_status=VehicleOwnershipStatus.PERSONAL,
                usage_type=VehicleUsageType.PERSONAL,
                quota_mode=VehicleQuotaMode.OWNER_PERSONAL_QUOTA,
                plate_number_snapshot=shared_registry_vehicle.plate_number,
                ktp_nfc_id_snapshot=buyer_profile_a.ktp_nfc_id_snapshot,
            )
            ownership_b = VehicleOwnership(
                owner_type=VehicleOwnerType.BUYER_PROFILE,
                owner_id=buyer_profile_b.id,
                vehicle_id=shared_registry_vehicle.id,
                ownership_status=VehicleOwnershipStatus.PERSONAL,
                usage_type=VehicleUsageType.UMKM,
                quota_mode=VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA,
                plate_number_snapshot=shared_registry_vehicle.plate_number,
                ktp_nfc_id_snapshot=buyer_profile_b.ktp_nfc_id_snapshot,
            )
            session.add_all([ownership_a, ownership_b])
            await session.flush()

            final_doc = VehicleOwnershipDocument(
                vehicle_ownership_id=ownership_a.id,
                document_type=VehicleOwnershipDocumentType.STNK_PHOTO,
                storage_key=f"{ownership_a.id}/stnk-photo.jpg",
                original_filename="stnk-photo.jpg",
                mime_type="image/jpeg",
                file_size_bytes=15,
                checksum_sha256="checksum-a",
            )
            pending_request = VehicleOwnershipRequest(
                buyer_profile_id=buyer_profile_a.id,
                vehicle_id=pending_registry_vehicle.id,
                ownership_status=VehicleOwnershipStatus.PERSONAL,
                usage_type=VehicleUsageType.OJOL,
                quota_mode=VehicleQuotaMode.DEDICATED_VEHICLE_QUOTA,
                plate_number_snapshot=pending_registry_vehicle.plate_number,
                ktp_nfc_id_snapshot=buyer_profile_a.ktp_nfc_id_snapshot,
                status=VehicleOwnershipRequestStatus.PENDING,
            )
            session.add_all([final_doc, pending_request])
            await session.flush()

            request_doc = VehicleOwnershipRequestDocument(
                vehicle_ownership_request_id=pending_request.id,
                document_type=VehicleOwnershipDocumentType.PRODUCTIVE_BUSINESS_PROOF,
                storage_key=f"{pending_request.id}/productive-business-proof.pdf",
                original_filename="productive-business-proof.pdf",
                mime_type="application/pdf",
                file_size_bytes=14,
                checksum_sha256="checksum-b",
            )
            session.add(request_doc)
            await session.commit()

            shared_vehicle_storage_dir = VehicleService.STORAGE_ROOT / str(ownership_a.id)
            shared_vehicle_storage_dir.mkdir(parents=True, exist_ok=True)
            (shared_vehicle_storage_dir / "stnk-photo.jpg").write_bytes(b"final-doc-bytes")

            request_storage_dir = VehicleService.REQUEST_STORAGE_ROOT / str(pending_request.id)
            request_storage_dir.mkdir(parents=True, exist_ok=True)
            (request_storage_dir / "productive-business-proof.pdf").write_bytes(b"pending-doc-bytes")

            ids = {
                "kk_id": kk.id,
                "user_a_id": user_a.id,
                "user_b_id": user_b.id,
                "buyer_profile_a_id": buyer_profile_a.id,
                "buyer_profile_b_id": buyer_profile_b.id,
                "citizen_a_id": citizen_a.id,
                "citizen_b_id": citizen_b.id,
                "citizen_c_id": citizen_c.id,
                "shared_registry_vehicle_id": shared_registry_vehicle.id,
                "pending_registry_vehicle_id": pending_registry_vehicle.id,
                "ownership_a_id": ownership_a.id,
                "ownership_b_id": ownership_b.id,
                "final_doc_id": final_doc.id,
                "pending_request_id": pending_request.id,
                "request_doc_id": request_doc.id,
            }

        token = _build_buyer_token(str(ids["user_a_id"]))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            family_res = await ac.get(
                "/api/v1/family/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert family_res.status_code == 200
            family_body = family_res.json()
            assert len(family_body["members"]) == 3
            assert len(family_body["vehicles"]) == 1
            assert len(family_body["vehicles"][0]["holders"]) == 2

            detail_res = await ac.get(
                f"/api/v1/vehicle-ownerships/{ids['ownership_a_id']}/detail",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert detail_res.status_code == 200
            detail_body = detail_res.json()
            assert len(detail_body["holders_in_family"]) == 2

            pending_res = await ac.get(
                "/api/v1/vehicle-ownerships/submissions/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert pending_res.status_code == 200
            pending_body = pending_res.json()
            assert len(pending_body["items"]) == 1
            assert pending_body["items"][0]["status"] == "PENDING"

            pending_detail_res = await ac.get(
                f"/api/v1/vehicle-ownerships/submissions/{ids['pending_request_id']}/detail",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert pending_detail_res.status_code == 200
            pending_detail_body = pending_detail_res.json()
            assert pending_detail_body["request_id"] == str(ids["pending_request_id"])
            assert pending_detail_body["usage_type"] == "OJOL"
            assert len(pending_detail_body["documents"]) == 1

            final_doc_res = await ac.get(
                f"/api/v1/vehicle-ownerships/{ids['ownership_a_id']}/documents/{ids['final_doc_id']}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert final_doc_res.status_code == 200
            assert final_doc_res.content == b"final-doc-bytes"

            request_doc_res = await ac.get(
                f"/api/v1/vehicle-ownerships/submissions/{ids['pending_request_id']}/documents/{ids['request_doc_id']}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert request_doc_res.status_code == 200
            assert request_doc_res.content == b"pending-doc-bytes"

            approve_res = await ac.post(
                f"/api/v1/vehicle-ownerships/submissions/{ids['pending_request_id']}/accept",
                json={"review_note": "Approved from docs testing"},
            )
            assert approve_res.status_code == 200
            approve_body = approve_res.json()
            assert approve_body["status"] == "APPROVED"
            approved_ownership_id = approve_body["approved_vehicle_ownership_id"]

            approved_detail_res = await ac.get(
                f"/api/v1/vehicle-ownerships/{approved_ownership_id}/detail",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert approved_detail_res.status_code == 200
            approved_detail_body = approved_detail_res.json()
            assert approved_detail_body["usage_type"] == "OJOL"
            assert len(approved_detail_body["documents"]) == 1

            approved_doc_res = await ac.get(
                f"/api/v1/vehicle-ownerships/{approved_ownership_id}/documents/{approved_detail_body['documents'][0]['id']}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert approved_doc_res.status_code == 200
            assert approved_doc_res.content == b"pending-doc-bytes"

            ids["approved_ownership_id"] = approved_ownership_id
            ids["approved_doc_id"] = approved_detail_body["documents"][0]["id"]
    finally:
        async with AsyncSessionLocal() as session:
            if ids.get("request_doc_id") is not None:
                await session.execute(delete(VehicleOwnershipRequestDocument).where(VehicleOwnershipRequestDocument.id == ids["request_doc_id"]))
            if ids.get("pending_request_id") is not None:
                await session.execute(delete(VehicleOwnershipRequest).where(VehicleOwnershipRequest.id == ids["pending_request_id"]))
            if ids.get("approved_doc_id") is not None:
                await session.execute(delete(VehicleOwnershipDocument).where(VehicleOwnershipDocument.id == ids["approved_doc_id"]))
            if ids.get("approved_ownership_id") is not None:
                await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id == ids["approved_ownership_id"]))
            if ids.get("final_doc_id") is not None:
                await session.execute(delete(VehicleOwnershipDocument).where(VehicleOwnershipDocument.id == ids["final_doc_id"]))
            if ids.get("ownership_a_id") is not None:
                await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id == ids["ownership_a_id"]))
            if ids.get("ownership_b_id") is not None:
                await session.execute(delete(VehicleOwnership).where(VehicleOwnership.id == ids["ownership_b_id"]))
            if ids.get("kk_id") is not None:
                await session.execute(delete(KKSubsidyEligibility).where(KKSubsidyEligibility.kk_id == ids["kk_id"]))
            if ids.get("shared_registry_vehicle_id") is not None:
                await session.execute(delete(VehicleRegistryMockup).where(VehicleRegistryMockup.id == ids["shared_registry_vehicle_id"]))
            if ids.get("pending_registry_vehicle_id") is not None:
                await session.execute(delete(VehicleRegistryMockup).where(VehicleRegistryMockup.id == ids["pending_registry_vehicle_id"]))
            if ids.get("citizen_a_id") is not None:
                await session.execute(delete(CitizenRegistryMockup).where(CitizenRegistryMockup.id == ids["citizen_a_id"]))
            if ids.get("citizen_b_id") is not None:
                await session.execute(delete(CitizenRegistryMockup).where(CitizenRegistryMockup.id == ids["citizen_b_id"]))
            if ids.get("citizen_c_id") is not None:
                await session.execute(delete(CitizenRegistryMockup).where(CitizenRegistryMockup.id == ids["citizen_c_id"]))
            if ids.get("buyer_profile_a_id") is not None:
                await session.execute(delete(BuyerProfile).where(BuyerProfile.id == ids["buyer_profile_a_id"]))
            if ids.get("buyer_profile_b_id") is not None:
                await session.execute(delete(BuyerProfile).where(BuyerProfile.id == ids["buyer_profile_b_id"]))
            if ids.get("user_a_id") is not None:
                await session.execute(delete(User).where(User.id == ids["user_a_id"]))
            if ids.get("user_b_id") is not None:
                await session.execute(delete(User).where(User.id == ids["user_b_id"]))
            if ids.get("kk_id") is not None:
                await session.execute(delete(KK).where(KK.id == ids["kk_id"]))
            await session.commit()

        if shared_vehicle_storage_dir and shared_vehicle_storage_dir.exists():
            shutil.rmtree(shared_vehicle_storage_dir, ignore_errors=True)
        if request_storage_dir and request_storage_dir.exists():
            shutil.rmtree(request_storage_dir, ignore_errors=True)
        if ids.get("approved_ownership_id") is not None:
            approved_storage_dir = VehicleService.STORAGE_ROOT / str(ids["approved_ownership_id"])
            if approved_storage_dir.exists():
                shutil.rmtree(approved_storage_dir, ignore_errors=True)
