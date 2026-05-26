import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_company_registration():
    payload = {
        "name": "PT Test Logistics",
        "nib": "9120000000000",
        "email": "test@company.com",
        "phone": "081234567890",
        "fleet_size": "25",
        "siup_no": "SIUP-999",
        "tdp_no": "TDP-999",
        "npwp_no": "NPWP-999",
        "notes": "Testing fleet registration form integration."
    }
    
    files = {
        "siup_file": ("siup.pdf", b"dummy_pdf_content", "application/pdf"),
        "tdp_file": ("tdp.pdf", b"dummy_pdf_content", "application/pdf"),
    }
    
    response = client.post("/api/v1/companies/register", data=payload, files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "PT Test Logistics"
    assert data["status"] == "Belum Verifikasi"
    assert "siup" in data["siup_doc"]
    assert "tdp" in data["tdp_doc"]
