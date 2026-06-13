from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Site, SiteGroup, SiteGroupMember, User
from app.schemas import (
    GroupComparisonItem,
    SiteGroupCreate,
    SiteGroupResponse,
    SiteGroupUpdateSites,
)
from app.services.sync_service import get_group_comparison

router = APIRouter()


@router.get("", response_model=list[SiteGroupResponse])
async def list_groups(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SiteGroup).where(SiteGroup.user_id == user.id))
    groups = result.scalars().all()

    responses = []
    for group in groups:
        member_result = await db.execute(
            select(SiteGroupMember.site_id).where(SiteGroupMember.group_id == group.id)
        )
        site_ids = [row[0] for row in member_result.all()]
        responses.append(
            SiteGroupResponse(id=group.id, name=group.name, color=group.color, site_ids=site_ids)
        )
    return responses


@router.post("", response_model=SiteGroupResponse)
async def create_group(
    body: SiteGroupCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    group = SiteGroup(user_id=user.id, name=body.name, color=body.color)
    db.add(group)
    await db.flush()
    return SiteGroupResponse(id=group.id, name=group.name, color=group.color, site_ids=[])


@router.get("/compare", response_model=list[GroupComparisonItem])
async def compare_groups(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_group_comparison(db, user)


@router.put("/{group_id}/sites", response_model=SiteGroupResponse)
async def update_group_sites(
    group_id: int,
    body: SiteGroupUpdateSites,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SiteGroup).where(SiteGroup.id == group_id, SiteGroup.user_id == user.id)
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Validate sites belong to user
    site_result = await db.execute(select(Site.id).where(Site.user_id == user.id))
    valid_site_ids = {row[0] for row in site_result.all()}
    for site_id in body.site_ids:
        if site_id not in valid_site_ids:
            raise HTTPException(status_code=400, detail=f"Site {site_id} not found")

    existing = await db.execute(select(SiteGroupMember).where(SiteGroupMember.group_id == group_id))
    for member in existing.scalars().all():
        await db.delete(member)

    for site_id in body.site_ids:
        db.add(SiteGroupMember(group_id=group_id, site_id=site_id))

    await db.flush()
    return SiteGroupResponse(id=group.id, name=group.name, color=group.color, site_ids=body.site_ids)


@router.delete("/{group_id}")
async def delete_group(
    group_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SiteGroup).where(SiteGroup.id == group_id, SiteGroup.user_id == user.id)
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    await db.delete(group)
    return {"deleted": True}
