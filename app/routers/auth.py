from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import UserResponse
from app.services.gsc import get_google_oauth_flow, store_credentials_on_user
from app.services.security import create_access_token

router = APIRouter()


@router.get("/google")
async def google_login():
    flow = get_google_oauth_flow()
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return RedirectResponse(url=authorization_url)


@router.get("/callback")
async def google_callback(code: str, db: AsyncSession = Depends(get_db)):
    flow = get_google_oauth_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials

    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
        )
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch Google user info")
        idinfo = userinfo_resp.json()

    google_id = idinfo["id"]
    email = idinfo.get("email", "")
    name = idinfo.get("name")
    avatar = idinfo.get("picture")

    result = await db.execute(select(User).where(User.google_id == google_id))
    user = result.scalar_one_or_none()

    access_enc, refresh_enc, expiry = store_credentials_on_user(User(), creds)

    if not user:
        user = User(
            google_id=google_id,
            email=email,
            name=name,
            avatar_url=avatar,
            access_token_encrypted=access_enc,
            refresh_token_encrypted=refresh_enc,
            token_expiry=expiry,
        )
        db.add(user)
    else:
        user.email = email
        user.name = name
        user.avatar_url = avatar
        user.access_token_encrypted = access_enc
        user.refresh_token_encrypted = refresh_enc
        user.token_expiry = expiry

    await db.flush()

    token = create_access_token({"user_id": user.id, "email": user.email})
    redirect_url = f"{settings.frontend_url}/auth/callback?token={token}"
    return RedirectResponse(url=redirect_url)


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user
