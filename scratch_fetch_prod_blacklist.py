import httpx
import json

BASE_URL = "https://api.smkn1wringin.sch.id/api/v1"

async def main():
    async with httpx.AsyncClient(verify=False) as client:
        login_res = await client.post(f"{BASE_URL}/auth/login", json={
            "email": "super.admin@mysuf.id",
            "password": "mysuf123",
            "client_type": "ADMIN_WEB"
        })
        token = login_res.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        
        bl_res = await client.get(f"{BASE_URL}/government/blacklist", headers=headers)
        print(f"GET /government/blacklist: {bl_res.status_code}")
        if bl_res.status_code == 200:
            print(json.dumps(bl_res.json(), indent=2))
        else:
            print(bl_res.text)

import asyncio
if __name__ == "__main__":
    asyncio.run(main())
