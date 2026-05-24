from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from app.core.security import verify_password, create_access_token, create_refresh_token
from app.core.security import ALGORITHM
from app.core.config import settings
from app.core.exceptions import CredentialsException
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.auth.schemas import LoginRequest, LoginResponse, RefreshTokenRequest, UserAuthResponse
from app.modules.auth.utils import build_access_contexts, get_allowed_apps, validate_client_access

class AuthService:
    def __init__(self, db: AsyncSession):
        self.repo = UserRepository(db)

    async def login(self, request: LoginRequest) -> LoginResponse:
        user = await self.repo.get_user_by_email(request.email)
        
        if not user or not verify_password(request.password, user.password):
            raise CredentialsException(detail="Incorrect email or password")
            
        if not user.is_active:
            raise CredentialsException(detail="Inactive user")
            
        if not validate_client_access(user, request.client_type):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User does not have access to {request.client_type}"
            )
            
        return self._build_login_response(user=user, client_type=request.client_type)

    async def refresh(self, request: RefreshTokenRequest) -> LoginResponse:
        try:
            payload = jwt.decode(
                request.refresh_token,
                settings.SECRET_KEY,
                algorithms=[ALGORITHM],
            )
        except JWTError as exc:
            raise CredentialsException(detail="Invalid refresh token") from exc

        if payload.get("type") != "refresh":
            raise CredentialsException(detail="Invalid refresh token type")

        user_id = payload.get("sub")
        if not user_id:
            raise CredentialsException(detail="Invalid refresh token subject")

        user = await self.repo.get_user_by_id(user_id)
        if user is None:
            raise CredentialsException(detail="User not found")
        if not user.is_active:
            raise CredentialsException(detail="Inactive user")
        if not validate_client_access(user, request.client_type):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User does not have access to {request.client_type}"
            )

        session_id = payload.get("session_id") or str(uuid7())
        return self._build_login_response(
            user=user,
            client_type=request.client_type,
            session_id=session_id,
        )

    async def get_me_response(self, user: User, payload: dict) -> LoginResponse:
        client_type = payload.get("client_type", "ADMIN_WEB")
        session_id = payload.get("session_id", str(uuid7()))
        return self._build_login_response(user=user, client_type=client_type, session_id=session_id)

    def _build_login_response(self, user: User, client_type: str, session_id: str | None = None) -> LoginResponse:
        resolved_session_id = session_id or str(uuid7())
        roles = [r.value for r in user.role]
        allowed_apps = get_allowed_apps(user.role)

        access_token = create_access_token(
            subject=user.id,
            session_id=resolved_session_id,
            client_type=client_type,
            roles=roles,
            allowed_apps=allowed_apps,
        )
        refresh_token = create_refresh_token(
            subject=user.id,
            session_id=resolved_session_id,
        )

        contexts = build_access_contexts(user)
        user_resp = UserAuthResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            roles=user.role,
            access_contexts=contexts,
        )
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=user_resp,
            allowed_apps=allowed_apps,
        )
