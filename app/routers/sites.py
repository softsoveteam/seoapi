from datetime import datetime, timedelta

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Keyword, KeywordSnapshot, Site, SiteDailyMetric, User
from app.schemas import (
    KeywordResponse,
    KeywordSnapshotResponse,
    SiteDailyMetricResponse,
    SiteResponse,
    SiteWithTrendResponse,
    TrackKeywordsRequest,
)
from app.services.sync_service import get_site_with_trend, sync_sites_for_user, sync_site_keywords, sync_site_metrics

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=list[SiteWithTrendResponse])
async def list_sites(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Site).where(Site.user_id == user.id).order_by(Site.site_url))
    sites = result.scalars().all()
    return [await get_site_with_trend(db, site) for site in sites]


@router.post("/sync")
async def sync_sites_from_gsc(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        count = await sync_sites_for_user(db, user)
        return {"synced": count, "message": f"Synced {count} new sites from Search Console"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Site sync failed for user %s", user.id)
        raise HTTPException(status_code=500, detail=f"Site sync failed: {e}")


@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(
    site_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Site).where(Site.id == site_id, Site.user_id == user.id))
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


@router.get("/{site_id}/metrics", response_model=list[SiteDailyMetricResponse])
async def get_site_metrics(
    site_id: int,
    days: int = 30,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Site).where(Site.id == site_id, Site.user_id == user.id))
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    end = datetime.utcnow().date() - timedelta(days=3)
    start = end - timedelta(days=days - 1)

    metrics_result = await db.execute(
        select(SiteDailyMetric)
        .where(SiteDailyMetric.site_id == site_id, SiteDailyMetric.date >= start, SiteDailyMetric.date <= end)
        .order_by(SiteDailyMetric.date)
    )
    return metrics_result.scalars().all()


@router.post("/{site_id}/sync")
async def sync_single_site(
    site_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Site).where(Site.id == site_id, Site.user_id == user.id))
    site = result.scalar_one_or_none()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    try:
        metrics_count = await sync_site_metrics(db, site, user)
        keywords_count = await sync_site_keywords(db, site, user)
        return {
            "metrics_synced": metrics_count,
            "keyword_snapshots_synced": keywords_count,
            "last_synced_at": site.last_synced_at,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Single site sync failed for site %s", site_id)
        raise HTTPException(status_code=500, detail=f"Site sync failed: {e}")
