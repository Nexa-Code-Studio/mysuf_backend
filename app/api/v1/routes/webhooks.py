import json
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import settings
from app.modules.transactions.service import TransactionService

router = APIRouter()

@router.post("/xendit")
async def xendit_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Public webhook receiver for Xendit events.
    Secured via basic callback token pre-shared key validation.
    """
    # 1. Verify callback token in headers
    callback_token = request.headers.get("x-callback-token")
    if not callback_token or callback_token != settings.XENDIT_CALLBACK_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing callback token."
        )

    # 2. Extract raw body for precise database auditing
    raw_body = await request.body()
    raw_body_str = raw_body.decode("utf-8")

    # 3. Parse JSON safely
    try:
        payload = json.loads(raw_body_str)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON format."
        )

    # 4. Process payment transaction and credit wallet
    service = TransactionService(db)
    await service.process_webhook_payment(payload, raw_body_str)
    
    return {"status": "success", "message": "Webhook processed successfully"}
