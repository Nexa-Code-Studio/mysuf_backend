from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Dict, Any

from app.api.deps import get_db, get_current_user
from app.modules.users.models import User
from app.modules.notifications.schemas import NotificationResponse, NotificationListResponse
from app.modules.notifications.service import NotificationService

router = APIRouter()

@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List all notifications for the authenticated user.
    """
    notifications = await NotificationService.get_user_notifications(db, current_user.id)
    return NotificationListResponse(
        items=notifications,
        total=len(notifications)
    )

@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark a specific notification as read.
    """
    notification = await NotificationService.mark_as_read(
        db=db,
        user_id=current_user.id,
        notification_id=notification_id
    )
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    return notification

@router.post("/read-all", response_model=Dict[str, Any])
async def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark all unread notifications of the authenticated user as read.
    """
    count = await NotificationService.mark_all_as_read(db, current_user.id)
    return {
        "message": "All notifications marked as read",
        "count": count
    }
