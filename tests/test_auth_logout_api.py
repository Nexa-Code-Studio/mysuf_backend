from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.main import app
from app.modules.auth.models import AuthSessionRecord
from app.modules.gas_stations.models import GasStation
from app.modules.users.models import User, UserRole


@pytest.mark.anyio
async def test_logout_revokes_access_and_refresh_tokens():
    gas_station = GasStation(
        name=f"SPBU Logout {uuid4().hex[:6]}",
        longitude=106.8,
        latitude=-6.2,
    )
    cashier = User(
        name="Cashier Logout",
        email=f"cashier-logout-{uuid4().hex[:8]}@example.com",
        password=get_password_hash("secret123"),
        role=[UserRole.SALES_OFFICER],
        is_active=True,
    )

    gas_station_id = None
    cashier_id = None

    try:
        async with AsyncSessionLocal() as session:
            session.add(gas_station)
            await session.commit()
            await session.refresh(gas_station)

            cashier.gas_station_id = gas_station.id
            session.add(cashier)
            await session.commit()
            await session.refresh(cashier)

            gas_station_id = gas_station.id
            cashier_id = cashier.id

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            login_response = await ac.post(
                "/api/v1/auth/login",
                json={
                    "email": cashier.email,
                    "password": "secret123",
                    "client_type": "POS_ANDROID",
                },
            )

            assert login_response.status_code == 200
            login_body = login_response.json()
            access_token = login_body["access_token"]
            refresh_token = login_body["refresh_token"]

            me_response = await ac.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert me_response.status_code == 200

            logout_response = await ac.post(
                "/api/v1/auth/logout",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert logout_response.status_code == 200
            assert logout_response.json() == {"message": "Logged out successfully"}

            revoked_me_response = await ac.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert revoked_me_response.status_code == 401
            assert revoked_me_response.json()["detail"] == "Session has been revoked"

            refresh_response = await ac.post(
                "/api/v1/auth/refresh",
                json={
                    "refresh_token": refresh_token,
                    "client_type": "POS_ANDROID",
                },
            )
            assert refresh_response.status_code == 401
            assert refresh_response.json()["detail"] == "Session has been revoked"
    finally:
        async with AsyncSessionLocal() as session:
            if cashier_id is not None:
                await session.execute(delete(AuthSessionRecord).where(AuthSessionRecord.user_id == cashier_id))
                await session.execute(delete(User).where(User.id == cashier_id))
            if gas_station_id is not None:
                await session.execute(delete(GasStation).where(GasStation.id == gas_station_id))
            await session.commit()
