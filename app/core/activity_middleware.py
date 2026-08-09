import asyncio
import logging
from jose import jwt, JWTError
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from uuid import UUID

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.log_path_map import resolve_action
from app.modules.users.models import User, UserRole
from app.modules.spbu_activities.models import SpbuActivityLog, SpbuActivityCategory
from app.modules.system_audit_logs.models import SystemAuditLog

logger = logging.getLogger(__name__)

# Algoritma JWT
ALGORITHM = "HS256"


class ActivityLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Hanya log request mutasi data (POST, PUT, PATCH, DELETE)
        # Skip requests ke health check, openapi, docs, dll.
        method = request.method.upper()
        path = request.url.path

        is_mutation = method in ("POST", "PUT", "PATCH", "DELETE")
        is_ignored_path = any(
            path.startswith(prefix)
            for prefix in ("/health", "/docs", "/redoc", "/openapi.json")
        )

        if not is_mutation or is_ignored_path:
            return await call_next(request)

        # Ambil IP address sebelum request diproses
        ip_address = self._resolve_ip(request)

        # Coba ekstrak user info awal dari token JWT (non-blocking, hanya decode string)
        user_id = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
                user_id = payload.get("sub")
            except JWTError:
                pass

        # Teruskan request
        response = await call_next(request)

        # Jalankan logging secara asynchronous (fire-and-forget)
        # Dengan begini response langsung terkirim ke client tanpa menunggu DB write log
        asyncio.create_task(
            self._write_activity_log(
                user_id=user_id,
                method=method,
                path=path,
                ip_address=ip_address,
                status_code=response.status_code,
            )
        )

        return response

    def _resolve_ip(self, request: Request) -> str:
        for header in ("x-forwarded-for", "x-real-ip", "X-Forwarded-For", "X-Real-IP"):
            val = request.headers.get(header)
            if val:
                return val.split(",")[0].strip()
        return request.client.host if request.client else "127.0.0.1"

    async def _write_activity_log(
        self,
        user_id: str | None,
        method: str,
        path: str,
        ip_address: str,
        status_code: int,
    ) -> None:
        async with AsyncSessionLocal() as session:
            try:
                # 1. Ambil data user dari DB jika terautentikasi
                user = None
                if user_id:
                    from sqlalchemy import select
                    stmt = select(User).filter(User.id == UUID(user_id))
                    res = await session.execute(stmt)
                    user = res.scalar()

                # 2. Tentukan deskripsi human-readable dan kategori SPBU
                action_desc, spbu_cat = resolve_action(method, path)

                # Jika request gagal (status 4xx/5xx), tambahkan status di log
                if status_code >= 400:
                    action_desc = f"Gagal ({status_code}): {action_desc}"

                # 3. Klasifikasi user role untuk menentukan tabel log
                is_spbu_user = False
                actor_name = "System"
                actor_role = "System"
                gas_station_id = None

                if user:
                    actor_name = user.name
                    gas_station_id = user.gas_station_id
                    
                    # Cek roles
                    roles = user.role or []
                    is_spbu_user = any(
                        r in roles
                        for r in (UserRole.SPBU_ADMIN, UserRole.SALES_OFFICER)
                    )
                    
                    # Resolve primary role string
                    role_priority = [
                        (UserRole.SUPER_ADMIN, "Super Admin"),
                        (UserRole.GOV_ADMIN, "Admin Pemerintah"),
                        (UserRole.COMPANY_ADMIN, "Admin Perusahaan"),
                        (UserRole.SPBU_ADMIN, "Admin SPBU"),
                        (UserRole.SALES_OFFICER, "Sales Officer"),
                        (UserRole.BUYER, "Warga Komersial"),
                    ]
                    for r, label in role_priority:
                        if r in roles:
                            actor_role = label
                            break
                    else:
                        if roles:
                            actor_role = str(roles[0])

                # 4. Tulis ke tabel log yang sesuai
                # SPBU Activity Log
                if is_spbu_user and gas_station_id:
                    spbu_log = SpbuActivityLog(
                        gas_station_id=gas_station_id,
                        user_id=user.id if user else None,
                        category=spbu_cat,
                        detail=action_desc,
                    )
                    session.add(spbu_log)

                # System Audit Log (untuk semua admin & system log, termasuk SPBU admin audit trail)
                # Hanya skip jika role adalah Warga Komersial (BUYER) biasa
                if not user or (user and UserRole.BUYER not in user.role):
                    audit_log = SystemAuditLog(
                        actor_id=user.id if user else None,
                        actor_name_snapshot=actor_name,
                        actor_role_snapshot=actor_role,
                        action=action_desc,
                        ip_address=ip_address,
                    )
                    session.add(audit_log)

                await session.commit()

            except Exception as e:
                logger.error(f"Gagal menulis activity log ke database: {e}", exc_info=True)
                await session.rollback()
