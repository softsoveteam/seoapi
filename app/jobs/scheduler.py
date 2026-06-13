import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.routers.sync import scheduled_sync_all_users

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def start_scheduler():
    scheduler.add_job(
        scheduled_sync_all_users,
        trigger="cron",
        hour=settings.sync_hour,
        minute=0,
        id="daily_sync",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — daily sync at %s:00", settings.sync_hour)


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
