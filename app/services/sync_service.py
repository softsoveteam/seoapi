from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    AIReport,
    Keyword,
    KeywordSnapshot,
    Site,
    SiteDailyMetric,
    SiteGroup,
    SiteGroupMember,
    SyncJob,
    SyncJobStatus,
    SyncJobType,
    User,
)
from app.services.gsc import (
    build_search_console_service,
    default_sync_date_range,
    fetch_keyword_metrics,
    fetch_site_daily_metrics,
    get_credentials_for_user,
    list_verified_sites,
)

logger = logging.getLogger(__name__)


async def sync_sites_for_user(db: AsyncSession, user: User) -> int:
    creds = get_credentials_for_user(user)
    if not creds:
        raise ValueError(
            "Google credentials missing or expired. Please sign out and sign in again with Google."
        )

    try:
        service = build_search_console_service(creds)
        gsc_sites = list_verified_sites(service)
    except Exception as e:
        logger.exception("GSC sites.list failed for user %s", user.id)
        raise ValueError(f"Search Console API error: {e}") from e

    count = 0
    for entry in gsc_sites:
        site_url = entry.get("siteUrl")
        permission = entry.get("permissionLevel")
        if not site_url:
            continue

        result = await db.execute(
            select(Site).where(Site.user_id == user.id, Site.site_url == site_url)
        )
        site = result.scalar_one_or_none()
        if not site:
            site = Site(user_id=user.id, site_url=site_url, permission_level=permission)
            db.add(site)
            count += 1
        else:
            site.permission_level = permission
            site.is_active = True
    await db.flush()
    return count


async def sync_site_metrics(db: AsyncSession, site: Site, user: User, days: int = 90) -> int:
    creds = get_credentials_for_user(user)
    if not creds:
        raise ValueError("No valid Google credentials")

    service = build_search_console_service(creds)
    start_date, end_date = default_sync_date_range(days)
    rows = fetch_site_daily_metrics(service, site.site_url, start_date, end_date)

    count = 0
    for row in rows:
        metric_date = datetime.strptime(row["date"], "%Y-%m-%d").date()
        result = await db.execute(
            select(SiteDailyMetric).where(
                SiteDailyMetric.site_id == site.id, SiteDailyMetric.date == metric_date
            )
        )
        metric = result.scalar_one_or_none()
        if not metric:
            metric = SiteDailyMetric(site_id=site.id, date=metric_date)
            db.add(metric)
            count += 1

        metric.clicks = row["clicks"]
        metric.impressions = row["impressions"]
        metric.ctr = row["ctr"]
        metric.avg_position = row["position"]

    site.last_synced_at = datetime.utcnow()
    await db.flush()
    return count


async def sync_site_keywords(db: AsyncSession, site: Site, user: User, days: int = 90) -> int:
    creds = get_credentials_for_user(user)
    if not creds:
        raise ValueError("No valid Google credentials")

    service = build_search_console_service(creds)
    start_date, end_date = default_sync_date_range(days)
    rows = fetch_keyword_metrics(service, site.site_url, start_date, end_date)

    count = 0
    for row in rows:
        query = row["query"]
        snapshot_date = datetime.strptime(row["date"], "%Y-%m-%d").date()

        result = await db.execute(
            select(Keyword).where(Keyword.site_id == site.id, Keyword.query == query)
        )
        keyword = result.scalar_one_or_none()
        if not keyword:
            keyword = Keyword(site_id=site.id, query=query, is_tracked=False)
            db.add(keyword)
            await db.flush()

        result = await db.execute(
            select(KeywordSnapshot).where(
                KeywordSnapshot.keyword_id == keyword.id, KeywordSnapshot.date == snapshot_date
            )
        )
        snapshot = result.scalar_one_or_none()
        if not snapshot:
            snapshot = KeywordSnapshot(keyword_id=keyword.id, date=snapshot_date)
            db.add(snapshot)
            count += 1

        snapshot.position = row["position"]
        snapshot.clicks = row["clicks"]
        snapshot.impressions = row["impressions"]
        snapshot.ctr = row["ctr"]

    await db.flush()
    return count


async def run_full_sync(db: AsyncSession, user_id: int | None = None) -> SyncJob:
    job = SyncJob(
        user_id=user_id,
        job_type=SyncJobType.FULL.value,
        status=SyncJobStatus.RUNNING.value,
        started_at=datetime.utcnow(),
    )
    db.add(job)
    await db.flush()

    try:
        if user_id:
            result = await db.execute(select(User).where(User.id == user_id))
            users = [result.scalar_one()]
        else:
            result = await db.execute(select(User))
            users = result.scalars().all()

        for user in users:
            await sync_sites_for_user(db, user)
            result = await db.execute(select(Site).where(Site.user_id == user.id, Site.is_active == True))
            sites = result.scalars().all()
            for site in sites:
                await sync_site_metrics(db, site, user)
                await sync_site_keywords(db, site, user)

        job.status = SyncJobStatus.COMPLETED.value
        job.completed_at = datetime.utcnow()
    except Exception as e:
        logger.exception("Sync failed")
        job.status = SyncJobStatus.FAILED.value
        job.error = str(e)
        job.completed_at = datetime.utcnow()

    await db.flush()
    return job


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 2)


def _trend_direction(change_pct: float) -> str:
    if change_pct >= settings.trend_threshold_percent:
        return "up"
    if change_pct <= -settings.trend_threshold_percent:
        return "down"
    return "stable"


async def _site_metrics_sum(
    db: AsyncSession, site_id: int, start: date, end: date
) -> tuple[int, int, float | None]:
    result = await db.execute(
        select(
            func.coalesce(func.sum(SiteDailyMetric.clicks), 0),
            func.coalesce(func.sum(SiteDailyMetric.impressions), 0),
            func.avg(SiteDailyMetric.avg_position),
        ).where(
            SiteDailyMetric.site_id == site_id,
            SiteDailyMetric.date >= start,
            SiteDailyMetric.date <= end,
        )
    )
    row = result.one()
    return int(row[0]), int(row[1]), float(row[2]) if row[2] is not None else None


async def get_site_with_trend(db: AsyncSession, site: Site) -> dict:
    today = datetime.utcnow().date()
    end = today - timedelta(days=3)
    start_7d = end - timedelta(days=6)
    start_prev_7d = start_7d - timedelta(days=7)
    end_prev_7d = start_7d - timedelta(days=1)

    clicks_7d, impressions_7d, avg_pos = await _site_metrics_sum(db, site.id, start_7d, end)
    clicks_prev, impressions_prev, _ = await _site_metrics_sum(db, site.id, start_prev_7d, end_prev_7d)
    change = _pct_change(clicks_7d, clicks_prev)

    return {
        "id": site.id,
        "site_url": site.site_url,
        "permission_level": site.permission_level,
        "is_active": site.is_active,
        "last_synced_at": site.last_synced_at,
        "clicks_7d": clicks_7d,
        "clicks_prev_7d": clicks_prev,
        "clicks_change_pct": change,
        "impressions_7d": impressions_7d,
        "trend": _trend_direction(change),
        "avg_position_7d": avg_pos,
    }


async def get_dashboard_summary(db: AsyncSession, user: User) -> dict:
    result = await db.execute(select(Site).where(Site.user_id == user.id, Site.is_active == True))
    sites = result.scalars().all()

    site_trends = [await get_site_with_trend(db, site) for site in sites]

    total_clicks_7d = sum(s["clicks_7d"] for s in site_trends)
    total_clicks_prev = sum(s["clicks_prev_7d"] for s in site_trends)
    total_impressions_7d = sum(s["impressions_7d"] for s in site_trends)

    winning = sorted(
        [s for s in site_trends if s["clicks_change_pct"] > 0],
        key=lambda x: x["clicks_change_pct"],
        reverse=True,
    )[:5]
    best = sorted(site_trends, key=lambda x: x["clicks_7d"], reverse=True)[:5]
    declining = sorted(
        [s for s in site_trends if s["clicks_change_pct"] < 0],
        key=lambda x: x["clicks_change_pct"],
    )[:5]

    today = datetime.utcnow().date()
    end = today - timedelta(days=3)
    start = end - timedelta(days=29)
    start_prev = start - timedelta(days=30)
    end_prev = start - timedelta(days=1)

    total_impressions_prev = 0
    for site in sites:
        _, imp_prev, _ = await _site_metrics_sum(db, site.id, start_prev, end_prev)
        total_impressions_prev += imp_prev

    chart_data: list[dict] = []
    for i in range(30):
        d = start + timedelta(days=i)
        if d > end:
            break
        day_result = await db.execute(
            select(func.coalesce(func.sum(SiteDailyMetric.clicks), 0)).where(
                SiteDailyMetric.site_id.in_([s.id for s in sites]),
                SiteDailyMetric.date == d,
            )
        )
        clicks = int(day_result.scalar() or 0)
        chart_data.append({"date": d.isoformat(), "clicks": clicks})

    last_sync = max((s.last_synced_at for s in sites if s.last_synced_at), default=None)

    return {
        "total_sites": len(sites),
        "total_clicks_7d": total_clicks_7d,
        "total_clicks_prev_7d": total_clicks_prev,
        "clicks_change_pct": _pct_change(total_clicks_7d, total_clicks_prev),
        "total_impressions_7d": total_impressions_7d,
        "impressions_change_pct": _pct_change(total_impressions_7d, total_impressions_prev),
        "winning_sites": winning,
        "best_performing_sites": best,
        "declining_sites": declining,
        "traffic_chart": chart_data,
        "last_sync_at": last_sync,
    }


async def get_group_comparison(db: AsyncSession, user: User) -> list[dict]:
    result = await db.execute(select(SiteGroup).where(SiteGroup.user_id == user.id))
    groups = result.scalars().all()

    today = datetime.utcnow().date()
    end = today - timedelta(days=3)
    start_7d = end - timedelta(days=6)
    start_prev_7d = start_7d - timedelta(days=7)
    end_prev_7d = start_7d - timedelta(days=1)

    comparisons = []
    for group in groups:
        member_result = await db.execute(
            select(SiteGroupMember.site_id).where(SiteGroupMember.group_id == group.id)
        )
        site_ids = [row[0] for row in member_result.all()]
        if not site_ids:
            comparisons.append(
                {
                    "group_id": group.id,
                    "group_name": group.name,
                    "color": group.color,
                    "site_count": 0,
                    "clicks_7d": 0,
                    "clicks_prev_7d": 0,
                    "clicks_change_pct": 0.0,
                    "impressions_7d": 0,
                    "avg_position": None,
                    "trend": "stable",
                }
            )
            continue

        clicks_7d = 0
        clicks_prev = 0
        impressions_7d = 0
        positions: list[float] = []

        for site_id in site_ids:
            c7, i7, pos = await _site_metrics_sum(db, site_id, start_7d, end)
            c_prev, _, _ = await _site_metrics_sum(db, site_id, start_prev_7d, end_prev_7d)
            clicks_7d += c7
            clicks_prev += c_prev
            impressions_7d += i7
            if pos is not None:
                positions.append(pos)

        change = _pct_change(clicks_7d, clicks_prev)
        avg_pos = round(sum(positions) / len(positions), 2) if positions else None

        comparisons.append(
            {
                "group_id": group.id,
                "group_name": group.name,
                "color": group.color,
                "site_count": len(site_ids),
                "clicks_7d": clicks_7d,
                "clicks_prev_7d": clicks_prev,
                "clicks_change_pct": change,
                "impressions_7d": impressions_7d,
                "avg_position": avg_pos,
                "trend": _trend_direction(change),
            }
        )

    return comparisons


async def generate_mistral_report(db: AsyncSession, user: User, report_type: str, site_id: int | None) -> AIReport:
    summary = await get_dashboard_summary(db, user)
    groups = await get_group_comparison(db, user)

    result = await db.execute(
        select(Keyword)
        .join(Site)
        .where(Site.user_id == user.id, Keyword.is_tracked == True)
        .limit(50)
    )
    tracked = result.scalars().all()

    keyword_data = []
    for kw in tracked:
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
        if latest and prev and latest.position and prev.position:
            pos_change = round(prev.position - latest.position, 2)
        keyword_data.append(
            {
                "query": kw.query,
                "position": latest.position if latest else None,
                "clicks": latest.clicks if latest else 0,
                "position_change": pos_change,
            }
        )

    context = {
        "report_type": report_type,
        "dashboard": summary,
        "groups": groups,
        "tracked_keywords": keyword_data,
        "site_id": site_id,
    }

    prompt = f"""You are an expert SEO analyst. Generate a detailed SEO report based on this Search Console data.
Report type: {report_type}

Data:
{json.dumps(context, default=str, indent=2)}

Provide:
1. Executive summary
2. Top winning and declining sites with actionable insights
3. Keyword opportunities and position changes
4. Group performance comparison if groups exist
5. Prioritized action plan (what to work on first)

Format response as JSON with keys: title, summary, sections (array of {{heading, content}}), action_items (array of strings).
Also include a full markdown version in key "markdown"."""

    headers = {"Authorization": f"Bearer {settings.mistral_api_key}", "Content-Type": "application/json"}
    payload = {
        "model": settings.mistral_model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers=headers,
            json=payload,
        )
        if response.status_code != 200:
            raise ValueError(f"Mistral API error: {response.text}")
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)

    report = AIReport(
        user_id=user.id,
        report_type=report_type,
        title=parsed.get("title", f"{report_type.replace('_', ' ').title()} Report"),
        content_json=json.dumps(parsed),
        content_markdown=parsed.get("markdown", content),
    )
    db.add(report)
    await db.flush()
    return report
