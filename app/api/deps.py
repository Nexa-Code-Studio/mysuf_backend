from typing import List

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

from app.modules.users.models import User, UserRole
from app.modules.auth.utils import has_any_role
from app.core.exceptions import CredentialsException, ForbiddenException
from app.modules.auth.service import AuthService

async def get_current_user_with_payload(
    db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> tuple[User, dict]:
    auth_service = AuthService(db)
    payload = auth_service.decode_token(token)
    user_id: str = payload.get("sub")
    if user_id is None:
        raise CredentialsException(detail="Could not validate credentials")
    session_id = payload.get("session_id")
    client_type = payload.get("client_type")
    if session_id:
        await auth_service.ensure_session_is_active(
            session_id,
            user_id=user_id,
            client_type=client_type,
        )
    
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(User).options(selectinload(User.buyer_profile)).filter(User.id == user_id)
    )
    user = result.scalars().first()
    
    if user is None:
        raise CredentialsException(detail="User not found")
    if not user.is_active:
        raise CredentialsException(detail="Inactive user")
        
    return user, payload

oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login", auto_error=False)

async def get_optional_current_user_with_payload(
    db: AsyncSession = Depends(get_db), token: str | None = Depends(oauth2_scheme_optional)
) -> tuple[User, dict] | None:
    if not token:
        return None
    auth_service = AuthService(db)
    try:
        payload = auth_service.decode_token(token)
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        session_id = payload.get("session_id")
        client_type = payload.get("client_type")
        if session_id:
            await auth_service.ensure_session_is_active(
                session_id,
                user_id=user_id,
                client_type=client_type,
            )
    except CredentialsException:
        return None
    
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(User).options(selectinload(User.buyer_profile)).filter(User.id == user_id)
    )
    user = result.scalars().first()
    
    if user is None or not user.is_active:
        return None
        
    return user, payload

async def get_optional_current_user(
    user_and_payload: tuple[User, dict] | None = Depends(get_optional_current_user_with_payload)
) -> User | None:
    if user_and_payload is None:
        return None
    return user_and_payload[0]

async def get_current_user(
    user_and_payload: tuple[User, dict] = Depends(get_current_user_with_payload)
) -> User:
    return user_and_payload[0]

def require_roles(allowed_roles: List[UserRole]):
    def role_checker(current_user: User = Depends(get_current_user)):
        if not has_any_role(current_user, allowed_roles):
            raise ForbiddenException(detail="Operation not permitted")
        return current_user
    return role_checker
