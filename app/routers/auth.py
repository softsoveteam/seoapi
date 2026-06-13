import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.config import resolved_frontend_url, resolved_google_redirect_uri, settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import UserResponse
from app.services.gsc import get_google_oauth_flow, store_credentials_on_user
from app.services.security import create_access_token

logger = logging.getLogger(__name__)

router = APIRouter()


def _login_error_redirect(message: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"{resolved_frontend_url()}/login?error={message}",
    )


@router.get("/google")
async def google_login():
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured on the server")

    if not resolved_google_redirect_uri():
        raise HTTPException(status_code=500, detail="GOOGLE_REDIRECT_URI is not configured")

    flow = get_google_oauth_flow()
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return RedirectResponse(url=authorization_url)


@router.get("/callback")
async def google_callback(
    code: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    if error:
        logger.warning("Google OAuth error: %s", error)
        return _login_error_redirect(error)

    if not code:
        return _login_error_redirect("missing_code")

    if not settings.google_client_id or not settings.google_client_secret:
        logger.error("Google OAuth credentials missing")
        return _login_error_redirect("oauth_not_configured")

    try:
        flow = get_google_oauth_flow()
        flow.fetch_token(code=code)
        creds = flow.credentials

        if not creds or not creds.token:
            logger.error("Google token exchange returned no access token")
            return _login_error_redirect("no_access_token")

        async with httpx.AsyncClient(timeout=30.0) as client:
            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {creds.token}"},
            )
            if userinfo_resp.status_code != 200:
                logger.error("Userinfo failed: %s", userinfo_resp.text)
                return _login_error_redirect("userinfo_failed")
            idinfo = userinfo_resp.json()

        google_id = idinfo.get("id")
        if not google_id:
            return _login_error_redirect("invalid_userinfo")

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

        if not user.id:
            logger.error("User id missing after flush")
            return _login_error_redirect("user_save_failed")

        token = create_access_token({"user_id": user.id, "email": user.email})
        frontend = resolved_frontend_url()
        logger.info("OAuth success — redirecting to %s", frontend)
        redirect_url = f"{frontend}/auth/callback?token={token}"
        return RedirectResponse(url=redirect_url)

    except Exception:
        logger.exception("OAuth callback failed")
        return _login_error_redirect("oauth_callback_failed")


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user
