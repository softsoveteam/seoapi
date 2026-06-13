from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import AIReport, User
from app.schemas import AIReportResponse, ReportGenerateRequest
from app.services.sync_service import generate_mistral_report

router = APIRouter()


@router.get("", response_model=list[AIReportResponse])
async def list_reports(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AIReport).where(AIReport.user_id == user.id).order_by(AIReport.generated_at.desc()).limit(50)
    )
    return result.scalars().all()


@router.get("/{report_id}", response_model=AIReportResponse)
async def get_report(
    report_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AIReport).where(AIReport.id == report_id, AIReport.user_id == user.id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.post("/generate", response_model=AIReportResponse)
async def generate_report(
    body: ReportGenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.config import settings

    if not settings.mistral_api_key:
        raise HTTPException(status_code=400, detail="Mistral API key not configured")

    report = await generate_mistral_report(db, user, body.report_type, body.site_id)
    return report
