from typing import Any
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user_with_payload
from app.modules.users.models import User
from app.modules.auth.schemas import LoginRequest, LoginResponse
from app.modules.auth.service import AuthService

router = APIRouter()

@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db)
) -> Any:
    service = AuthService(db)
    return await service.login(request)

@router.get("/me", response_model=LoginResponse)
async def read_users_me(
    user_and_payload: tuple[User, dict] = Depends(get_current_user_with_payload),
    db: AsyncSession = Depends(get_db)
) -> Any:
    user, payload = user_and_payload
    service = AuthService(db)
    return await service.get_me_response(user, payload)
