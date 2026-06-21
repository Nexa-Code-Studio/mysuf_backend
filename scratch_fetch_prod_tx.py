import httpx
import json

BASE_URL = "https://api.smkn1wringin.sch.id/api/v1"

async def test_summary(email, password, role_name):
    print(f"\n=== Testing as {role_name} ({email}) ===")
    async with httpx.AsyncClient(verify=False) as client:
        # 1. Login
        try:
            login_res = await client.post(f"{BASE_URL}/auth/login", json={
                "email": email,
                "password": password,
                "client_type": "ADMIN_WEB"
            })
            if login_res.status_code != 200:
                print(f"Login failed: {login_res.status_code}")
                return
            
            token = login_res.json().get("access_token")
            headers = {"Authorization": f"Bearer {token}"}
            
            # Fetch summary
            if "gov" in email or "super" in email:
                summary_res = await client.get(f"{BASE_URL}/government/summary", headers=headers)
                print(f"GET /government/summary: {summary_res.status_code}")
                if summary_res.status_code == 200:
                    data = summary_res.json()
                    # print keys or relevant stats
                    print(json.dumps(data, indent=2)[:1000])
                else:
                    print(summary_res.text)
            else:
                summary_res = await client.get(f"{BASE_URL}/spbu/dashboard/summary", headers=headers)
                print(f"GET /spbu/dashboard/summary: {summary_res.status_code}")
                if summary_res.status_code == 200:
                    data = summary_res.json()
                    print(json.dumps(data, indent=2)[:1000])
                else:
                    print(summary_res.text)
                    
        except Exception as e:
            print(f"Exception: {e}")

import asyncio
async def main():
    await test_summary("super.admin@mysuf.id", "mysuf123", "Super Admin")
    await test_summary("gov.admin@mysuf.id", "mysuf123", "Gov Admin")
    await test_summary("spbu.admin@mysuf.id", "mysuf123", "SPBU Admin")

if __name__ == "__main__":
    asyncio.run(main())
