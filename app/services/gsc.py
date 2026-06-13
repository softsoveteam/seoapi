from __future__ import annotations

from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.config import settings
from app.models import User
from app.services.security import decrypt_token, encrypt_token

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/webmasters.readonly",
]


def get_google_oauth_flow():
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.google_redirect_uri],
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.google_redirect_uri,
    )
    return flow


def get_credentials_for_user(user: User) -> Credentials | None:
    if not user.access_token_encrypted:
        return None

    creds = Credentials(
        token=decrypt_token(user.access_token_encrypted),
        refresh_token=decrypt_token(user.refresh_token_encrypted or "") or None,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=SCOPES,
    )
    if user.token_expiry and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def store_credentials_on_user(user: User, creds: Credentials) -> tuple[str, str | None, datetime | None]:
    access_enc = encrypt_token(creds.token)
    refresh_enc = encrypt_token(creds.refresh_token) if creds.refresh_token else None
    expiry = creds.expiry
    return access_enc, refresh_enc, expiry


def build_search_console_service(creds: Credentials):
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


def list_verified_sites(service) -> list[dict]:
    response = service.sites().list().execute()
    return response.get("siteEntry", [])


def fetch_site_daily_metrics(service, site_url: str, start_date: str, end_date: str) -> list[dict]:
    request = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": ["date"],
        "rowLimit": 25000,
    }
    response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
    rows = response.get("rows", [])
    return [
        {
            "date": row["keys"][0],
            "clicks": int(row.get("clicks", 0)),
            "impressions": int(row.get("impressions", 0)),
            "ctr": float(row.get("ctr", 0)),
            "position": float(row.get("position", 0)),
        }
        for row in rows
    ]


def fetch_keyword_metrics(service, site_url: str, start_date: str, end_date: str) -> list[dict]:
    request = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": ["query", "date"],
        "rowLimit": 25000,
    }
    response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
    rows = response.get("rows", [])
    return [
        {
            "query": row["keys"][0],
            "date": row["keys"][1],
            "clicks": int(row.get("clicks", 0)),
            "impressions": int(row.get("impressions", 0)),
            "ctr": float(row.get("ctr", 0)),
            "position": float(row.get("position", 0)),
        }
        for row in rows
    ]


def default_sync_date_range(days: int = 90) -> tuple[str, str]:
    end = datetime.utcnow().date() - timedelta(days=3)
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()
