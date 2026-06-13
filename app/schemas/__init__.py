from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: Optional[str] = None
    avatar_url: Optional[str] = None


class SiteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_url: str
    permission_level: Optional[str] = None
    is_active: bool
    last_synced_at: Optional[datetime] = None


class SiteWithTrendResponse(SiteResponse):
    clicks_7d: int = 0
    clicks_prev_7d: int = 0
    clicks_change_pct: float = 0.0
    impressions_7d: int = 0
    trend: str = "stable"


class SiteDailyMetricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    clicks: int
    impressions: int
    ctr: float
    avg_position: Optional[float] = None


class KeywordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    site_id: int
    query: str
    is_tracked: bool
    latest_position: Optional[float] = None
    latest_clicks: int = 0
    latest_impressions: int = 0
    position_change: Optional[float] = None


class KeywordSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    position: Optional[float] = None
    clicks: int
    impressions: int
    ctr: float


class SiteGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str
    site_ids: List[int] = []


class SiteGroupCreate(BaseModel):
    name: str
    color: str = "#6366f1"


class SiteGroupUpdateSites(BaseModel):
    site_ids: List[int]


class GroupComparisonItem(BaseModel):
    group_id: int
    group_name: str
    color: str
    site_count: int
    clicks_7d: int
    clicks_prev_7d: int
    clicks_change_pct: float
    impressions_7d: int
    avg_position: Optional[float] = None
    trend: str


class DashboardSummary(BaseModel):
    total_sites: int
    total_clicks_7d: int
    total_clicks_prev_7d: int
    clicks_change_pct: float
    total_impressions_7d: int
    impressions_change_pct: float
    winning_sites: List[SiteWithTrendResponse]
    best_performing_sites: List[SiteWithTrendResponse]
    declining_sites: List[SiteWithTrendResponse]
    traffic_chart: List[Dict[str, Any]]
    last_sync_at: Optional[datetime] = None


class TrackKeywordsRequest(BaseModel):
    keyword_ids: List[int]
    is_tracked: bool = True


class ReportGenerateRequest(BaseModel):
    report_type: str = "weekly_summary"
    site_id: Optional[int] = None


class AIReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_type: str
    title: str
    content_json: str
    content_markdown: str
    generated_at: datetime


class SyncTriggerResponse(BaseModel):
    job_id: int
    status: str
    message: str
