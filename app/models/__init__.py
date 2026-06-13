from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional


from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SyncJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SyncJobType(str, Enum):
    FULL = "full"
    SITES = "sites"
    METRICS = "metrics"
    KEYWORDS = "keywords"


class ReportType(str, Enum):
    WEEKLY_SUMMARY = "weekly_summary"
    SITE_DEEP_DIVE = "site_deep_dive"
    KEYWORD_OPPORTUNITIES = "keyword_opportunities"
    ACTION_PLAN = "action_plan"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    google_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    access_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sites: Mapped[list["Site"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    site_groups: Mapped[list["SiteGroup"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    ai_reports: Mapped[list["AIReport"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    site_url: Mapped[str] = mapped_column(String(512), index=True)
    permission_level: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="sites")
    keywords: Mapped[list["Keyword"]] = relationship(back_populates="site", cascade="all, delete-orphan")
    daily_metrics: Mapped[list["SiteDailyMetric"]] = relationship(back_populates="site", cascade="all, delete-orphan")
    group_memberships: Mapped[list["SiteGroupMember"]] = relationship(back_populates="site", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("user_id", "site_url", name="uq_user_site_url"),)


class SiteGroup(Base):
    __tablename__ = "site_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    color: Mapped[str] = mapped_column(String(32), default="#6366f1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="site_groups")
    members: Mapped[list["SiteGroupMember"]] = relationship(back_populates="group", cascade="all, delete-orphan")


class SiteGroupMember(Base):
    __tablename__ = "site_group_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("site_groups.id", ondelete="CASCADE"), index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)

    group: Mapped["SiteGroup"] = relationship(back_populates="members")
    site: Mapped["Site"] = relationship(back_populates="group_memberships")

    __table_args__ = (UniqueConstraint("group_id", "site_id", name="uq_group_site"),)


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    query: Mapped[str] = mapped_column(String(512), index=True)
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    site: Mapped["Site"] = relationship(back_populates="keywords")
    snapshots: Mapped[list["KeywordSnapshot"]] = relationship(back_populates="keyword", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("site_id", "query", name="uq_site_query"),)


class KeywordSnapshot(Base):
    __tablename__ = "keyword_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id", ondelete="CASCADE"), index=True)
    date: Mapped[datetime] = mapped_column(Date, index=True)
    position: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    ctr: Mapped[float] = mapped_column(Float, default=0.0)

    keyword: Mapped["Keyword"] = relationship(back_populates="snapshots")

    __table_args__ = (
        UniqueConstraint("keyword_id", "date", name="uq_keyword_date"),
        Index("ix_keyword_snapshots_keyword_date", "keyword_id", "date"),
    )


class SiteDailyMetric(Base):
    __tablename__ = "site_daily_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    date: Mapped[datetime] = mapped_column(Date, index=True)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    ctr: Mapped[float] = mapped_column(Float, default=0.0)
    avg_position: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    site: Mapped["Site"] = relationship(back_populates="daily_metrics")

    __table_args__ = (
        UniqueConstraint("site_id", "date", name="uq_site_date"),
        Index("ix_site_daily_metrics_site_date", "site_id", "date"),
    )


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    job_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default=SyncJobStatus.PENDING.value)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AIReport(Base):
    __tablename__ = "ai_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    report_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    content_json: Mapped[str] = mapped_column(Text)
    content_markdown: Mapped[str] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="ai_reports")
