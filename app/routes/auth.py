import secrets
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import (
    get_default_provider,
    get_provider_config,
)

router = APIRouter(prefix="/auth", tags=["auth"])
TOKEN_CACHE_PATH = Path("token_cache.json")

# Session-backed token store persisted to disk for local development
TOKEN_STORE: dict[str, dict] = {}


def _write_token_store() -> None:
    TOKEN_CACHE_PATH.write_text(json.dumps(TOKEN_STORE, indent=2), encoding="utf-8")


def load_token_store() -> None:
    if not TOKEN_CACHE_PATH.exists():
        return

    try:
        raw = json.loads(TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return

    if not isinstance(raw, dict):
        return

    # Ignore legacy single-token cache formats that were not keyed by session_id.
    if "access_token" in raw:
        return

    TOKEN_STORE.clear()
    for session_id, token_data in raw.items():
        if isinstance(session_id, str) and isinstance(token_data, dict):
            TOKEN_STORE[session_id] = token_data


def persist_session_token(session_id: str, token_data: dict) -> None:
    TOKEN_STORE[session_id] = token_data
    _write_token_store()


def remove_session_token(session_id: str) -> None:
    if session_id in TOKEN_STORE:
        TOKEN_STORE.pop(session_id, None)
        _write_token_store()


def _expires_soon(token_data: dict, skew_seconds: int = 120) -> bool:
    obtained_at = token_data.get("obtained_at")
    expires_in = token_data.get("expires_in")
    if not obtained_at or not expires_in:
        return False

    try:
        expires_at = datetime.fromisoformat(obtained_at) + timedelta(seconds=int(expires_in))
    except Exception:
        return False

    return datetime.now(timezone.utc) >= (expires_at - timedelta(seconds=skew_seconds))


async def refresh_token_data(token_data: dict) -> dict:
    refresh_token = token_data.get("refresh_token")
    provider = token_data.get("provider", get_default_provider())
    provider_config = get_provider_config(provider)

    if not refresh_token:
        return token_data

    refresh_payload = {
        "client_id": provider_config["client_id"],
        "client_secret": provider_config["client_secret"],
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": provider_config["scope_delimiter"].join(provider_config["scopes"]),
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        if provider_config["provider"] == "zoho":
            response = await client.post(provider_config["token_url"], params=refresh_payload)
        else:
            response = await client.post(
                provider_config["token_url"],
                data=refresh_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

    if response.status_code != 200:
        return token_data

    refreshed = response.json()
    refreshed["provider"] = provider_config["provider"]
    refreshed["provider_label"] = provider_config["label"]
    refreshed["mailbox_email"] = token_data.get("mailbox_email") or provider_config["mailbox_email"]
    refreshed["refresh_token"] = refreshed.get("refresh_token") or refresh_token
    refreshed["obtained_at"] = datetime.now(timezone.utc).isoformat()
    token_data.clear()
    token_data.update(refreshed)
    return token_data


async def ensure_valid_token_data(token_data: dict) -> dict:
    if _expires_soon(token_data):
        return await refresh_token_data(token_data)
    return token_data


async def ensure_valid_session_token(session_id: str | None) -> dict | None:
    if not session_id:
        return None

    token_data = TOKEN_STORE.get(session_id)
    if not token_data:
        return None

    before_snapshot = json.dumps(token_data, sort_keys=True)
    token_data = await ensure_valid_token_data(token_data)
    after_snapshot = json.dumps(token_data, sort_keys=True)
    if after_snapshot != before_snapshot:
        persist_session_token(session_id, token_data)

    return token_data


@router.get("/login")
async def login(request: Request, provider: str | None = None):
    try:
        provider_config = get_provider_config(provider)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})

    state = secrets.token_urlsafe(32)
    session_id = secrets.token_urlsafe(16)

    request.session.clear()
    request.session["oauth_state"] = state
    request.session["session_id"] = session_id
    request.session["provider"] = provider_config["provider"]

    params = {
        "client_id": provider_config["client_id"],
        "response_type": "code",
        "redirect_uri": provider_config["redirect_uri"],
        "scope": provider_config["scope_delimiter"].join(provider_config["scopes"]),
        "state": state,
    }
    params.update(provider_config["auth_params"])

    auth_url = f"{provider_config['authorize_url']}?{urlencode(params)}"
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": error,
                "details": "The mail provider returned an error during login.",
            },
        )

    saved_state = request.session.get("oauth_state")
    session_id = request.session.get("session_id")
    provider = request.session.get("provider", get_default_provider())

    try:
        provider_config = get_provider_config(provider)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "provider_config_invalid",
                "details": str(exc),
            },
        )

    if not state or state != saved_state:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "invalid_state",
                "details": "State validation failed.",
                "returned_state": state,
                "saved_state": saved_state,
                "session_contents": dict(request.session),
            },
        )

    if not code:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "missing_code",
                "details": "No authorization code returned.",
            },
        )

    if not session_id:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "missing_session_id",
                "details": "Session ID missing.",
            },
        )

    token_payload = {
        "client_id": provider_config["client_id"],
        "client_secret": provider_config["client_secret"],
        "code": code,
        "redirect_uri": provider_config["redirect_uri"],
        "grant_type": "authorization_code",
        "scope": provider_config["scope_delimiter"].join(provider_config["scopes"]),
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        if provider_config["provider"] == "zoho":
            token_response = await client.post(provider_config["token_url"], params=token_payload)
        else:
            token_response = await client.post(
                provider_config["token_url"],
                data=token_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

    if token_response.status_code != 200:
        try:
            provider_error = token_response.json()
        except Exception:
            provider_error = {"raw_response": token_response.text}

        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": "token_exchange_failed",
                "provider_response": provider_error,
            },
        )

    tokens = token_response.json()
    tokens["provider"] = provider_config["provider"]
    tokens["provider_label"] = provider_config["label"]
    tokens["mailbox_email"] = provider_config["mailbox_email"]
    tokens["obtained_at"] = datetime.now(timezone.utc).isoformat()

    # Store full tokens server-side, not in cookie session
    persist_session_token(session_id, tokens)

    # Keep only small values in the cookie session
    request.session["authenticated"] = True
    request.session["provider"] = provider_config["provider"]
    request.session.pop("oauth_state", None)

    return JSONResponse(
        status_code=200,
        content={
            "ok": True,
            "message": "Login successful",
            "provider": provider_config["provider"],
            "token_type": tokens.get("token_type"),
            "expires_in": tokens.get("expires_in"),
            "has_access_token": bool(tokens.get("access_token")),
            "has_refresh_token": bool(tokens.get("refresh_token")),
        },
    )


@router.get("/logout")
async def logout(request: Request):
    session_id = request.session.get("session_id")
    if session_id:
        remove_session_token(session_id)

    request.session.clear()
    return {"ok": True, "message": "Logged out successfully"}


@router.get("/token-status")
async def token_status(request: Request):
    session_id = request.session.get("session_id")
    authenticated = request.session.get("authenticated", False)
    provider = request.session.get("provider")

    if not session_id or not authenticated or session_id not in TOKEN_STORE:
        return {
            "ok": False,
            "authenticated": False,
        }

    token_data = await ensure_valid_session_token(session_id)
    if not token_data:
        return {
            "ok": False,
            "authenticated": False,
        }

    return {
        "ok": True,
        "authenticated": True,
        "provider": provider,
        "token_type": token_data.get("token_type"),
        "expires_in": token_data.get("expires_in"),
        "scope": token_data.get("scope"),
    }
