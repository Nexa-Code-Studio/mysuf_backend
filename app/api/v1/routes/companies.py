import mimetypes
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_roles
from app.modules.companies.service import CompanyService, STORAGE_ROOT
from app.modules.companies.schemas import CompanyCreate, CompanyVerifyRequest, CompanyResponse
from app.modules.users.models import UserRole

router = APIRouter()


@router.post("/register", response_model=CompanyResponse)
async def register_company(
    name: str = Form(...),
    nib: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    fleet_size: int = Form(...),
    siup_no: Optional[str] = Form(None),
    tdp_no: Optional[str] = Form(None),
    npwp_no: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    siup_file: Optional[UploadFile] = File(None),
    tdp_file: Optional[UploadFile] = File(None),
    npwp_file: Optional[UploadFile] = File(None),
    nib_file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
):
    service = CompanyService(db)
    try:
        data = CompanyCreate(
            name=name,
            nib=nib,
            email=email,
            phone=phone,
            fleet_size=fleet_size,
            siup_no=siup_no,
            tdp_no=tdp_no,
            npwp_no=npwp_no,
            notes=notes,
        )
        return await service.register_company(
            data=data,
            siup_file=siup_file,
            tdp_file=tdp_file,
            npwp_file=npwp_file,
            nib_file=nib_file,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/documents/{company_id}/{filename}")
async def get_company_document(
    company_id: str,
    filename: str,
    current_user=Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN])),
):
    """
    Serve a company document stored under storage/companies/{company_id}/{filename}.
    Restricted to SUPER_ADMIN and GOV_ADMIN.
    """
    # Prevent path traversal
    if ".." in company_id or ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Nama berkas tidak valid.")

    file_path: Path = STORAGE_ROOT / company_id / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Berkas tidak ditemukan.")

    mime_type, _ = mimetypes.guess_type(filename)
    return FileResponse(
        path=file_path,
        media_type=mime_type or "application/octet-stream",
        filename=filename,
    )


@router.get("/", response_model=List[CompanyResponse])
async def get_companies(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN])),
):
    service = CompanyService(db)
    return await service.get_all_companies()


@router.put("/{company_id}/verify", response_model=CompanyResponse)
async def verify_company(
    request: Request,
    company_id: UUID,
    req: CompanyVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles([UserRole.SUPER_ADMIN, UserRole.GOV_ADMIN])),
):
    service = CompanyService(db)
    try:
        company = await service.verify_company(company_id, req)
        
        # Audit logging
        from app.modules.system_audit_logs.service import SystemAuditLogService
        ip = SystemAuditLogService.resolve_ip(request)
        audit_svc = SystemAuditLogService(db)
        
        action_word = "Approve" if req.status == "VERIFIED" else "Reject"
        await audit_svc.log_action(
            actor=current_user,
            action=f"{action_word} perusahaan: {company.name}",
            ip_address=ip
        )
        return company
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
