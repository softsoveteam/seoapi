from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Keyword, KeywordSnapshot, Site, User
from app.schemas import KeywordResponse, KeywordSnapshotResponse, TrackKeywordsRequest

router = APIRouter()


@router.get("", response_model=list[KeywordResponse])
async def list_keywords(
    tracked_only: bool = False,
    site_id: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Keyword).join(Site).where(Site.user_id == user.id)
    if tracked_only:
        query = query.where(Keyword.is_tracked == True)
    if site_id:
        query = query.where(Keyword.site_id == site_id)

    result = await db.execute(query.order_by(Keyword.query).limit(500))
    keywords = result.scalars().all()

    responses = []
    for kw in keywords:
        snap_result = await db.execute(
            select(KeywordSnapshot)
            .where(KeywordSnapshot.keyword_id == kw.id)
            .order_by(KeywordSnapshot.date.desc())
            .limit(2)
        )
        snaps = snap_result.scalars().all()
        latest = snaps[0] if snaps else None
        prev = snaps[1] if len(snaps) > 1 else None
        pos_change = None
        if latest and prev and latest.position is not None and prev.position is not None:
            pos_change = round(prev.position - latest.position, 2)

        responses.append(
            KeywordResponse(
                id=kw.id,
                site_id=kw.site_id,
                query=kw.query,
                is_tracked=kw.is_tracked,
                latest_position=latest.position if latest else None,
                latest_clicks=latest.clicks if latest else 0,
                latest_impressions=latest.impressions if latest else 0,
                position_change=pos_change,
            )
        )
    return responses


@router.post("/track")
async def track_keywords(
    body: TrackKeywordsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    updated = 0
    for kw_id in body.keyword_ids:
        result = await db.execute(
            select(Keyword).join(Site).where(Keyword.id == kw_id, Site.user_id == user.id)
        )
        keyword = result.scalar_one_or_none()
        if keyword:
            keyword.is_tracked = body.is_tracked
            updated += 1
    return {"updated": updated}


@router.get("/{keyword_id}/history", response_model=list[KeywordSnapshotResponse])
async def keyword_history(
    keyword_id: int,
    days: int = 30,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Keyword).join(Site).where(Keyword.id == keyword_id, Site.user_id == user.id)
    )
    keyword = result.scalar_one_or_none()
    if not keyword:
        raise HTTPException(status_code=404, detail="Keyword not found")

    from datetime import datetime, timedelta

    end = datetime.utcnow().date() - timedelta(days=3)
    start = end - timedelta(days=days - 1)

    snap_result = await db.execute(
        select(KeywordSnapshot)
        .where(
            KeywordSnapshot.keyword_id == keyword_id,
            KeywordSnapshot.date >= start,
            KeywordSnapshot.date <= end,
        )
        .order_by(KeywordSnapshot.date)
    )
    return snap_result.scalars().all()
