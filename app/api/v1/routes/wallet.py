from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, require_roles
from app.modules.users.models import User, UserRole
from app.modules.wallets.schemas import WalletResponse
from app.modules.wallets.service import WalletService
from app.modules.transactions.schemas import (
    TopUpRequest,
    TopUpResponse,
    WalletTransactionResponse,
    PaginatedWalletTransactionsResponse
)
from app.modules.transactions.service import TransactionService

router = APIRouter()

@router.get("/balance", response_model=WalletResponse)
async def get_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Get the authenticated user's wallet and balance.
    If no wallet exists, one is lazily created.
    """
    service = WalletService(db)
    return await service.get_balance(current_user.id)


@router.post("/topups", response_model=TopUpResponse)
async def create_topup(
    request: TopUpRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Initiate a wallet top-up session with Xendit.
    Returns the Xendit payment link URL for user redirection.
    """
    service = TransactionService(db)
    return await service.create_topup_session(current_user.id, request.amount)


@router.get("/sessions/{session_id}", response_model=TopUpResponse)
async def sync_session(
    session_id: str,
    current_user: User = Depends(require_roles([UserRole.SUPERADMIN])),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Admin-only endpoint to retrieve session status directly from Xendit
    and sync the local database state. Useful if webhooks are delayed.
    """
    service = TransactionService(db)
    return await service.sync_session_from_xendit(session_id)


@router.get("/topups/{id}", response_model=TopUpResponse)
async def get_topup_status(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Get the status of a specific wallet top-up transaction.
    """
    service = TransactionService(db)
    return await service.get_topup_status(id, current_user.id)


@router.get("/transactions", response_model=PaginatedWalletTransactionsResponse)
async def get_wallet_transactions(
    page: int = 1,
    size: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Get paginated wallet transactions for the authenticated user.
    """
    service = TransactionService(db)
    return await service.get_wallet_transactions(current_user.id, page, size)


@router.get("/transactions/{id}", response_model=WalletTransactionResponse)
async def get_wallet_transaction_detail(
    id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Get full details of a specific wallet transaction by ID.
    """
    service = TransactionService(db)
    return await service.get_wallet_transaction_detail(id, current_user.id)
