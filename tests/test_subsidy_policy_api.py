from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.database import AsyncSessionLocal
from app.main import app
from app.modules.subsidies.seed_data import seed_subsidy_policies
from app.modules.vehicles.models import VehicleUsageType


TEST_POLICY_DATA = [
    {
        "name": "API Quota Personal",
        "usage_type": VehicleUsageType.PERSONAL,
        "monthly_quota_liters": Decimal("260.00"),
        "max_allowed_njkb": Decimal("260000000.00"),
        "is_active": True,
    },
    {
        "name": "API Quota OJOL",
        "usage_type": VehicleUsageType.OJOL,
        "monthly_quota_liters": Decimal("261.00"),
        "max_allowed_njkb": Decimal("261000000.00"),
        "is_active": True,
    },
    {
        "name": "API Quota UMKM",
        "usage_type": VehicleUsageType.UMKM,
        "monthly_quota_liters": Decimal("262.00"),
        "max_allowed_njkb": Decimal("262000000.00"),
        "is_active": True,
    },
    {
        "name": "API Quota Company Operational",
        "usage_type": VehicleUsageType.COMPANY_OPERATIONAL,
        "monthly_quota_liters": Decimal("263.00"),
        "max_allowed_njkb": Decimal("263000000.00"),
        "is_active": True,
    },
]


@pytest.mark.anyio
async def test_subsidy_policy_list_and_update_flow():
    try:
        async with AsyncSessionLocal() as session:
            await seed_subsidy_policies(session, TEST_POLICY_DATA)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            res = await ac.get("/api/v1/subsidies/policies")
            assert res.status_code == 200
            body = res.json()
            assert body["pagination"]["total"] >= 4

            personal_policy = next(item for item in body["items"] if item["usage_type"] == "PERSONAL")
            assert personal_policy["name"] == "API Quota Personal"

            update_res = await ac.put(
                f"/api/v1/subsidies/policies/{personal_policy['id']}",
                json={
                    "name": "API Quota Personal Updated",
                    "monthly_quota_liters": "275.00",
                    "max_allowed_njkb": "275000000.00",
                },
            )
            assert update_res.status_code == 200
            updated = update_res.json()
            assert updated["usage_type"] == "PERSONAL"
            assert updated["name"] == "API Quota Personal Updated"
            assert Decimal(updated["monthly_quota_liters"]) == Decimal("275.00")
            assert Decimal(updated["max_allowed_njkb"]) == Decimal("275000000.00")
    finally:
        async with AsyncSessionLocal() as session:
            await seed_subsidy_policies(session)
