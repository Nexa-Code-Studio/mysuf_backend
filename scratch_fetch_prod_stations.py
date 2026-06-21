import httpx
import json

BASE_URL = "https://api.smkn1wringin.sch.id/api/v1"

async def main():
    async with httpx.AsyncClient(verify=False) as client:
        login_res = await client.post(f"{BASE_URL}/auth/login", json={
            "email": "gov.admin@mysuf.id",
            "password": "mysuf123",
            "client_type": "ADMIN_WEB"
        })
        token = login_res.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        
        heatmap_res = await client.get(f"{BASE_URL}/government/heatmap", headers=headers)
        if heatmap_res.status_code == 200:
            data = heatmap_res.json()
            features = data.get("map_data", {}).get("features", [])
            print(f"Total features: {len(features)}")
            for idx, f in enumerate(features):
                props = f.get("properties", {})
                print(f"{idx+1}. {props.get('id')} - fraud_cases: {props.get('fraud_cases')}, intensity: {props.get('intensity')}")
        else:
            print("Failed to fetch heatmap:", heatmap_res.text)

import asyncio
async def main_run():
    await main()

if __name__ == "__main__":
    asyncio.run(main_run())
