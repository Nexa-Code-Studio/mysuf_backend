from typing import Generator, List
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

# async def get_current_user(
#     db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)
# ):
#     pass
#
# def require_roles(allowed_roles: List[str]):
#     def role_checker(current_user = Depends(get_current_user)):
#         pass
#     return role_checker
