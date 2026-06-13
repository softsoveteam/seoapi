from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import SyncTriggerResponse
from app.services.sync_service import run_full_sync

router = APIRouter()


@router.post("/trigger", response_model=SyncTriggerResponse)
async def trigger_sync(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await run_full_sync(db, user.id)
    return SyncTriggerResponse(
        job_id=job.id,
        status=job.status,
        message="Sync completed" if job.status == "completed" else f"Sync failed: {job.error}",
    )


async def scheduled_sync_all_users():
    async with async_session() as db:
        try:
            await run_full_sync(db, user_id=None)
            await db.commit()
        except Exception:
            await db.rollback()
            raise
