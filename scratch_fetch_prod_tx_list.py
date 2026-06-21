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
        
        # We need an endpoint to list all transactions
        # Let's see: maybe we can query /government/summary? No, that is summary.
        # Wait, is there a transaction history list endpoint in the API?
        # Let's search government routes for endpoints listing transactions.
        # Oh, in /home/mashupsoat/Project/mysuf/mysuf_backend/app/api/v1/routes/government.py:
        # line 268: @router.get("/quota-transactions", response_model=GovernmentQuotaTransactionResponse)
        # Wait, let's look at the routes list.
        # Let's try fetching `/government/quota-transactions` or `/spbu/transactions` (wait, spbu admin can fetch transactions).
        # Let's fetch both or see what we can query!
        
        q_res = await client.get(f"{BASE_URL}/government/quota-transactions", headers=headers)
        print(f"GET /government/quota-transactions: {q_res.status_code}")
        if q_res.status_code == 200:
            print(json.dumps(q_res.json(), indent=2))
        else:
            print(q_res.text)

import asyncio
if __name__ == "__main__":
    asyncio.run(main())
