from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.modules.gas_stations.models import GasStation
from app.modules.registries.models import KK
from app.modules.users.models import BuyerProfile, User, UserRole, VerificationStatus


def _build_buyer_token(user_id: str) -> str:
    return create_access_token(
        subject=user_id,
        session_id=str(uuid4()),
        client_type="BUYER_ANDROID",
        roles=[UserRole.BUYER.value],
        allowed_apps=["BUYER_ANDROID"],
    )


@pytest.mark.anyio
async def test_get_nearby_gas_stations_returns_sorted_items_with_limit():
    kk = KK(code=f"KK-NEARBY-{uuid4().hex[:8]}")
    user = User(
        name="Nearby Buyer",
        email=f"nearby-buyer-{uuid4().hex[:8]}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.BUYER],
        is_active=True,
    )
    buyer_profile = BuyerProfile(
        nik_snapshot=f"3171{uuid4().hex[:12]}",
        ktp_nfc_id_snapshot=f"NFC-{uuid4().hex[:8]}",
        kk=kk,
        user=user,
        verification_status=VerificationStatus.VERIFIED,
        risk_score=Decimal("10.00"),
    )
    station_near = GasStation(name=f"SPBU Near {uuid4().hex[:6]}", latitude=-6.2000, longitude=106.8000)
    station_mid = GasStation(name=f"SPBU Mid {uuid4().hex[:6]}", latitude=-6.2500, longitude=106.8500)
    station_far = GasStation(name=f"SPBU Far {uuid4().hex[:6]}", latitude=-7.2000, longitude=107.8000)

    ids: dict[str, object] = {}

    try:
        async with AsyncSessionLocal() as session:
            session.add_all([kk, user, buyer_profile, station_near, station_mid, station_far])
            await session.commit()
            await session.refresh(kk)
            await session.refresh(user)
            await session.refresh(buyer_profile)
            await session.refresh(station_near)
            await session.refresh(station_mid)
            await session.refresh(station_far)

            ids = {
                "kk_id": kk.id,
                "user_id": user.id,
                "buyer_profile_id": buyer_profile.id,
                "station_near_id": station_near.id,
                "station_mid_id": station_mid.id,
                "station_far_id": station_far.id,
            }

        token = _build_buyer_token(str(ids["user_id"]))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(
                "/api/v1/users/me/nearby-gas-stations",
                params={"latitude": -6.2001, "longitude": 106.8001, "limit": 2},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["location_available"] is True
        assert body["message"] is None
        assert len(body["items"]) == 2
        assert body["items"][0]["name"] == station_near.name
        assert body["items"][1]["name"] == station_mid.name
        assert body["items"][0]["distance_km"] <= body["items"][1]["distance_km"]
    finally:
        async with AsyncSessionLocal() as session:
            if ids.get("station_near_id") is not None:
                await session.execute(delete(GasStation).where(GasStation.id == ids["station_near_id"]))
            if ids.get("station_mid_id") is not None:
                await session.execute(delete(GasStation).where(GasStation.id == ids["station_mid_id"]))
            if ids.get("station_far_id") is not None:
                await session.execute(delete(GasStation).where(GasStation.id == ids["station_far_id"]))
            if ids.get("buyer_profile_id") is not None:
                await session.execute(delete(BuyerProfile).where(BuyerProfile.id == ids["buyer_profile_id"]))
            if ids.get("user_id") is not None:
                await session.execute(delete(User).where(User.id == ids["user_id"]))
            if ids.get("kk_id") is not None:
                await session.execute(delete(KK).where(KK.id == ids["kk_id"]))
            await session.commit()


@pytest.mark.anyio
async def test_get_nearby_gas_stations_returns_location_message_without_coordinates():
    kk = KK(code=f"KK-NEARBY-{uuid4().hex[:8]}")
    user = User(
        name="Nearby Buyer Missing Coords",
        email=f"nearby-missing-{uuid4().hex[:8]}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.BUYER],
        is_active=True,
    )
    buyer_profile = BuyerProfile(
        nik_snapshot=f"3171{uuid4().hex[:12]}",
        ktp_nfc_id_snapshot=f"NFC-{uuid4().hex[:8]}",
        kk=kk,
        user=user,
        verification_status=VerificationStatus.VERIFIED,
        risk_score=Decimal("5.00"),
    )

    ids: dict[str, object] = {}

    try:
        async with AsyncSessionLocal() as session:
            session.add_all([kk, user, buyer_profile])
            await session.commit()
            await session.refresh(kk)
            await session.refresh(user)
            await session.refresh(buyer_profile)

            ids = {
                "kk_id": kk.id,
                "user_id": user.id,
                "buyer_profile_id": buyer_profile.id,
            }

        token = _build_buyer_token(str(ids["user_id"]))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.get(
                "/api/v1/users/me/nearby-gas-stations",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["location_available"] is False
        assert body["items"] == []
        assert body["message"] == "Lokasi Anda tidak ditemukan, tolong nyalakan GPS."
    finally:
        async with AsyncSessionLocal() as session:
            if ids.get("buyer_profile_id") is not None:
                await session.execute(delete(BuyerProfile).where(BuyerProfile.id == ids["buyer_profile_id"]))
            if ids.get("user_id") is not None:
                await session.execute(delete(User).where(User.id == ids["user_id"]))
            if ids.get("kk_id") is not None:
                await session.execute(delete(KK).where(KK.id == ids["kk_id"]))
            await session.commit()
