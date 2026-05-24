import logging
from typing import List, Optional, Any
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification
from app.modules.users.models import User
from app.core.notifications import FCMService

logger = logging.getLogger(__name__)

class NotificationService:
    @staticmethod
    async def create_notification(
        db: AsyncSession,
        user_id: UUID,
        title: str,
        body: str,
        data: Optional[dict] = None
    ) -> Notification:
        """
        Creates and persists a notification in the database,
        then dispatches it via FCM push notification if user has a registered token.
        """
        # 1. Create and persist Notification
        notification = Notification(
            user_id=user_id,
            title=title,
            body=body,
            data=data,
            is_read=False
        )
        db.add(notification)
        await db.commit()
        await db.refresh(notification)

        # 2. Query user's fcm_token and trigger Push Notification
        try:
            user = await db.get(User, user_id)
            if user and user.fcm_token:
                # Dispatch push in a safe try-except block so push errors don't roll back the DB transaction
                await FCMService.send_push_notification(
                    token=user.fcm_token,
                    title=title,
                    body=body,
                    data=data
                )
        except Exception as fcm_err:
            logger.error(f"Failed to dispatch FCM push inside create_notification: {fcm_err}")

        return notification

    @staticmethod
    async def get_user_notifications(db: AsyncSession, user_id: UUID) -> List[Notification]:
        """
        Retrieves all notifications for a specific user, sorted from newest to oldest.
        """
        stmt = select(Notification).filter(Notification.user_id == user_id).order_by(Notification.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def mark_as_read(db: AsyncSession, user_id: UUID, notification_id: UUID) -> Optional[Notification]:
        """
        Marks a specific notification as read.
        """
        stmt = select(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == user_id
        )
        result = await db.execute(stmt)
        notification = result.scalars().first()
        if notification:
            notification.is_read = True
            await db.commit()
            await db.refresh(notification)
        return notification

    @staticmethod
    async def mark_all_as_read(db: AsyncSession, user_id: UUID) -> int:
        """
        Marks all unread notifications of a specific user as read.
        """
        stmt = (
            update(Notification)
            .filter(Notification.user_id == user_id, Notification.is_read == False)
            .values(is_read=True)
            .execution_options(synchronize_session="fetch")
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount
