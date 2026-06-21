import httpx
import json

BASE_URL = "https://api.smkn1wringin.sch.id/api/v1"

async def test_endpoint(email, password, role_name):
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
                print(f"Login failed: {login_res.status_code} - {login_res.text}")
                return
            
            token_data = login_res.json()
            token = token_data.get("access_token")
            headers = {"Authorization": f"Bearer {token}"}
            print("Login successful! Token acquired.")
            
            # 2. Fetch fraud logs
            logs_res = await client.get(f"{BASE_URL}/fraud-logs", headers=headers)
            print(f"GET /fraud-logs: {logs_res.status_code}")
            if logs_res.status_code == 200:
                logs_data = logs_res.json()
                print(f"  Total count: {logs_data.get('total_count')}")
                print(f"  Items count: {len(logs_data.get('items', []))}")
                print(f"  Stats: {logs_data.get('stats')}")
                if logs_data.get('items'):
                    print(f"  First 3 items:")
                    for idx, item in enumerate(logs_data['items'][:3]):
                        print(f"    - ID: {item.get('id')}, case_id: {item.get('case_id')}, risk_score: {item.get('risk_score')}, risk_level: {item.get('risk_level')}, station: {item.get('gas_station_name')}")
            else:
                print(f"  Failed: {logs_res.text}")

            # 3. Fetch government heatmap if role is GOV_ADMIN or SUPER_ADMIN
            if "admin" in email:
                heatmap_res = await client.get(f"{BASE_URL}/government/heatmap", headers=headers)
                print(f"GET /government/heatmap: {heatmap_res.status_code}")
                if heatmap_res.status_code == 200:
                    heatmap_data = heatmap_res.json()
                    provinces = heatmap_data.get("provinces", [])
                    print(f"  Provinces count: {len(provinces)}")
                    # print sum of fraud cases
                    fraud_sum = sum(p.get("fraudScore", 0) for p in provinces)
                    print(f"  Fraud score sum: {fraud_sum}")
                    features = heatmap_data.get("map_data", {}).get("features", [])
                    print(f"  Map features count: {len(features)}")
                    feat_fraud_sum = sum(f.get("properties", {}).get("fraud_cases", 0) for f in features)
                    print(f"  Map features fraud cases sum: {feat_fraud_sum}")
                else:
                    print(f"  Failed: {heatmap_res.text}")
                    
        except Exception as e:
            print(f"Exception: {e}")

import asyncio
async def main():
    await test_endpoint("super.admin@mysuf.id", "mysuf123", "Super Admin")
    await test_endpoint("gov.admin@mysuf.id", "mysuf123", "Gov Admin")
    await test_endpoint("spbu.admin@mysuf.id", "mysuf123", "SPBU Admin")

if __name__ == "__main__":
    asyncio.run(main())
