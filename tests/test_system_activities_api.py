import pytest
from httpx import AsyncClient, ASGITransport
from uuid import uuid4
from sqlalchemy import delete, select
from datetime import datetime, timedelta

from app.main import app
from app.core.database import AsyncSessionLocal
from app.modules.users.models import User, UserRole
from app.modules.system_audit_logs.models import SystemAuditLog
from app.core.security import get_password_hash, create_access_token

@pytest.mark.anyio
async def test_system_activities_api():
    super_admin_id = uuid4()
    buyer_id = uuid4()

    async with AsyncSessionLocal() as session:
        # Create Super Admin User
        super_admin = User(
            id=super_admin_id,
            name="Super Admin Activity Logger",
            email=f"super-admin-act-{uuid4().hex[:8]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.SUPER_ADMIN],
            is_active=True
        )
        session.add(super_admin)

        # Create Buyer User
        buyer = User(
            id=buyer_id,
            name="Buyer User Activity Logger",
            email=f"buyer-act-{uuid4().hex[:8]}@example.com",
            password=get_password_hash("password123"),
            role=[UserRole.BUYER],
            is_active=True
        )
        session.add(buyer)
        await session.commit()


    # Generate Auth Tokens
    super_token = create_access_token(
        subject=super_admin_id,
        session_id=str(uuid4()),
        client_type="DASHBOARD",
        roles=["SUPER_ADMIN"],
        allowed_apps=["DASHBOARD"]
    )
    headers_super = {"Authorization": f"Bearer {super_token}"}

    buyer_token = create_access_token(
        subject=buyer_id,
        session_id=str(uuid4()),
        client_type="MOBILE",
        roles=["BUYER"],
        allowed_apps=["MOBILE"]
    )
    headers_buyer = {"Authorization": f"Bearer {buyer_token}"}

    try:
        # Clear any system audit logs created by other tests to ensure a clean slate
        async with AsyncSessionLocal() as session:
            await session.execute(delete(SystemAuditLog))
            
            # Seed 5 mockup audit logs explicitly for the test assertions
            now = datetime.utcnow()
            mock_data = [
                ("Rama Utama", "Super Admin", "Approve perusahaan: PT Logistik Nusantara Maju", "103.24.118.12", now - timedelta(minutes=5)),
                ("Sari Widodo", "Admin Pemerintah", "Update bobot kelayakan: NJKB 40%", "180.252.91.44", now - timedelta(minutes=17)),
                ("Rama Utama", "Super Admin", "Reject warga komersial: KTP 3174012345678901", "103.24.118.12", now - timedelta(hours=10, minutes=30)),
                ("Dewi Kusuma", "Admin Perusahaan", "Reset MFA akun perusahaan", "36.85.101.77", now - timedelta(hours=13, minutes=5)),
                ("Rama Utama", "Super Admin", "Tambah user baru: Admin SPBU Bandung", "103.24.118.12", now - timedelta(hours=13, minutes=45)),
            ]

            for name, role, action, ip, created_at in mock_data:
                log_entry = SystemAuditLog(
                    actor_id=None,
                    actor_name_snapshot=name,
                    actor_role_snapshot=role,
                    action=action,
                    ip_address=ip,
                    created_at=created_at
                )
                session.add(log_entry)
            await session.commit()


        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Test 1: Fetch activity logs as BUYER (should get 403 Forbidden)
            res_buyer = await ac.get("/api/v1/mysuf-admin/audit-logs", headers=headers_buyer)
            assert res_buyer.status_code == 403

            # Test 2: Fetch activity logs as SUPER_ADMIN (should automatically seed 5 mockup items)
            res_super = await ac.get("/api/v1/mysuf-admin/audit-logs", headers=headers_super)
            assert res_super.status_code == 200
            data = res_super.json()
            assert data["total"] >= 5
            assert len(data["items"]) >= 5

            # Verify that the seeded logs exist
            actions = [item["action"] for item in data["items"]]
            assert any("Approve perusahaan: PT Logistik Nusantara Maju" in action for action in actions)

            # Test 3: Search filter
            res_search = await ac.get("/api/v1/mysuf-admin/audit-logs?search=PT%20Logistik", headers=headers_super)
            assert res_search.status_code == 200
            data_search = res_search.json()
            assert len(data_search["items"]) == 1
            assert "PT Logistik Nusantara Maju" in data_search["items"][0]["action"]

            # Test 4: Trigger audit log on user creation via API
            new_user_email = f"new-user-{uuid4().hex[:8]}@example.com"
            user_payload = {
                "name": "Audit Test User",
                "email": new_user_email,
                "password": "Password123!",
                "role": ["BUYER"]
            }
            res_create = await ac.post("/api/v1/users/", json=user_payload, headers=headers_super)
            assert res_create.status_code == 201
            created_user_id = res_create.json()["id"]

            # Fetch logs again and verify trigger was logged
            res_audit_after = await ac.get("/api/v1/mysuf-admin/audit-logs", headers=headers_super)
            assert res_audit_after.status_code == 200
            actions_after = [item["action"] for item in res_audit_after.json()["items"]]
            assert "Tambah user baru: Audit Test User" in actions_after

            # Clean up the created user
            res_delete = await ac.delete(f"/api/v1/users/{created_user_id}", headers=headers_super)
            assert res_delete.status_code == 204

            # Verify delete trigger was logged
            res_audit_final = await ac.get("/api/v1/mysuf-admin/audit-logs", headers=headers_super)
            assert res_audit_final.status_code == 200
            actions_final = [item["action"] for item in res_audit_final.json()["items"]]
            assert "Hapus user: Audit Test User" in actions_final

    finally:
        # Cleanup
        async with AsyncSessionLocal() as session:
            await session.execute(delete(SystemAuditLog))
            await session.execute(delete(User).where(User.id.in_([super_admin_id, buyer_id])))
            await session.commit()
