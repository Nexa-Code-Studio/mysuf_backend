from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from uuid_extensions import uuid7

from app.core.security import verify_password, create_access_token, create_refresh_token
from app.core.security import ALGORITHM
from app.core.config import settings
from app.core.exceptions import CredentialsException
from app.modules.auth.models import AuthSessionRecord
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.auth.schemas import LoginRequest, LoginResponse, LogoutResponse, RefreshTokenRequest, UserAuthResponse
from app.modules.auth.utils import build_access_contexts, get_allowed_apps, validate_client_access


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UserRepository(db)

    async def login(self, request: LoginRequest) -> LoginResponse:
        user = await self.repo.get_user_by_email(request.email)
        
        if not user or not verify_password(request.password, user.password):
            raise CredentialsException(detail="Incorrect email or password")
            
        if not user.is_active:
            raise CredentialsException(detail="Inactive user")
            
        from app.modules.users.service import UserService
        UserService.check_user_fraud_status(user)
            
        if not validate_client_access(user, request.client_type):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User does not have access to {request.client_type}"
            )
            
        return await self._build_login_response(user=user, client_type=request.client_type)

    async def refresh(self, request: RefreshTokenRequest) -> LoginResponse:
        payload = self.decode_token(request.refresh_token, detail="Invalid refresh token")

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
            
        from app.modules.users.service import UserService
        UserService.check_user_fraud_status(user)
        if not validate_client_access(user, request.client_type):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User does not have access to {request.client_type}"
            )

        session_id = payload.get("session_id") or str(uuid7())
        await self.ensure_session_is_active(
            session_id,
            user_id=str(user.id),
            client_type=request.client_type,
        )
        return await self._build_login_response(
            user=user,
            client_type=request.client_type,
            session_id=session_id,
        )

    async def get_me_response(self, user: User, payload: dict) -> LoginResponse:
        client_type = payload.get("client_type", "ADMIN_WEB")
        session_id = payload.get("session_id", str(uuid7()))
        return await self._build_login_response(user=user, client_type=client_type, session_id=session_id)

    async def logout(self, user: User, payload: dict) -> LogoutResponse:
        session_id = payload.get("session_id")
        if not session_id:
            raise CredentialsException(detail="Invalid access token session")

        client_type = payload.get("client_type", "ADMIN_WEB")
        expires_at = self._resolve_session_expiry(payload)
        await self.revoke_session(
            session_id,
            user_id=user.id,
            client_type=client_type,
            expires_at=expires_at,
        )
        return LogoutResponse(message="Logged out successfully")

    async def ensure_session_is_active(
        self,
        session_id: str,
        *,
        user_id: str | None = None,
        client_type: str | None = None,
    ) -> None:
        session_record = await self._get_session_record(session_id)
        if session_record is None:
            return

        if session_record.revoked_at is not None:
            raise CredentialsException(detail="Session has been revoked")
        if user_id is not None and str(session_record.user_id) != user_id:
            raise CredentialsException(detail="Session user mismatch")
        if client_type is not None and session_record.client_type != client_type:
            raise CredentialsException(detail="Session client mismatch")

    async def revoke_session(
        self,
        session_id: str,
        *,
        user_id: str | UUID,
        client_type: str,
        expires_at: datetime | None = None,
    ) -> None:
        session_record = await self._get_session_record(session_id)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if session_record is None:
            session_record = AuthSessionRecord(
                session_id=session_id,
                user_id=self._coerce_user_id(user_id),
                client_type=client_type,
                issued_at=now,
                expires_at=expires_at or now + timedelta(days=7),
                revoked_at=now,
            )
            self.db.add(session_record)
        else:
            session_record.revoked_at = now
            if expires_at is not None and expires_at > session_record.expires_at:
                session_record.expires_at = expires_at

        await self.db.commit()

    def decode_token(self, token: str, *, detail: str = "Could not validate credentials") -> dict:
        try:
            return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError as exc:
            raise CredentialsException(detail=detail) from exc

    async def _build_login_response(self, user: User, client_type: str, session_id: str | None = None) -> LoginResponse:
        resolved_session_id = session_id or str(uuid7())
        roles = [r.value for r in user.role]
        allowed_apps = get_allowed_apps(user.role)
        refresh_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)

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
        await self._upsert_session_record(
            session_id=resolved_session_id,
            user_id=str(user.id),
            client_type=client_type,
            expires_at=refresh_expires_at,
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

    async def _get_session_record(self, session_id: str) -> AuthSessionRecord | None:
        result = await self.db.execute(
            select(AuthSessionRecord).filter(AuthSessionRecord.session_id == session_id)
        )
        return result.scalars().first()

    async def _upsert_session_record(
        self,
        *,
        session_id: str,
        user_id: str | UUID,
        client_type: str,
        expires_at: datetime,
    ) -> None:
        session_record = await self._get_session_record(session_id)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if session_record is None:
            self.db.add(
                AuthSessionRecord(
                    session_id=session_id,
                    user_id=self._coerce_user_id(user_id),
                    client_type=client_type,
                    issued_at=now,
                    expires_at=expires_at,
                )
            )
        else:
            session_record.user_id = self._coerce_user_id(user_id)
            session_record.client_type = client_type
            session_record.expires_at = expires_at
            session_record.revoked_at = None

        await self.db.commit()

    def _resolve_session_expiry(self, payload: dict) -> datetime:
        exp = payload.get("exp")
        if exp is None:
            return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)
        return datetime.fromtimestamp(exp, tz=timezone.utc).replace(tzinfo=None) + timedelta(days=7)

    def _coerce_user_id(self, user_id: str | UUID) -> UUID:
        if isinstance(user_id, UUID):
            return user_id
        return UUID(str(user_id))
