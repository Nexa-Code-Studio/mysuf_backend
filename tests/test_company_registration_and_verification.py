import pytest
from uuid import uuid4
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

from app.main import app
from app.core.database import AsyncSessionLocal
from app.modules.companies.models import Company


@pytest.mark.anyio
async def test_company_registration():
    # Use a unique NIB to avoid clashing with previous test runs
    unique_nib = f"912{uuid4().int % 10000000000:010d}"
    payload = {
        "name": "PT Test Logistics",
        "nib": unique_nib,
        "email": f"test-logistics-{uuid4().hex[:8]}@company.com",
        "phone": "081234567890",
        "fleet_size": "25",
        "siup_no": "SIUP-999",
        "tdp_no": "TDP-999",
        "npwp_no": "NPWP-999",
        "notes": "Testing fleet registration form integration."
    }

    files = [
        ("siup_file", ("siup.pdf", b"dummy_pdf_content", "application/pdf")),
        ("tdp_file", ("tdp.pdf", b"dummy_pdf_content", "application/pdf")),
    ]

    company_id = None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/companies/register",
                data=payload,
                files=files,
            )
        assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.text}"
        data = response.json()
        assert data["name"] == "PT Test Logistics"
        assert data["status"] == "Belum Verifikasi"
        assert data["siup_doc"] is not None and "siup" in data["siup_doc"]
        assert data["tdp_doc"] is not None and "tdp" in data["tdp_doc"]
        company_id = data["id"]
    finally:
        if company_id:
            async with AsyncSessionLocal() as session:
                await session.execute(delete(Company).where(Company.id == company_id))
                await session.commit()
        else:
            # Fallback cleanup in case company was created before assertion failure
            async with AsyncSessionLocal() as session:
                await session.execute(delete(Company).where(Company.nib == unique_nib))
                await session.commit()
