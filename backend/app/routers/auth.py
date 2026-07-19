import os
import secrets
import logging
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import BarberShop, User
from ..schemas import LoginRequest, UserRead
from ..security import create_access_token, get_current_user, hash_password, is_platform_admin, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)

FRONTEND_URL = os.getenv("APP_BASE_URL", "http://localhost:5173")
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def public_user(user: User) -> UserRead:
    return UserRead(id=user.id, email=user.email, role="platform_admin" if is_platform_admin(user) else user.role)


def set_login_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        key="access_token", value=create_access_token(user), httponly=True,
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true", samesite="lax", max_age=60 * 60 * 8,
    )


@router.post("/login", response_model=UserRead)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email, User.is_active.is_(True)))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if user.google_subject:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Use Continue with Google for this account")
    user.last_login_at = datetime.utcnow()
    db.commit()
    set_login_cookie(response, user)
    return public_user(user)


@router.get("/google/login")
def google_login(next: str = "login"):
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    state = secrets.token_urlsafe(32)
    callback_url = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")
    url = f"{GOOGLE_AUTH_URL}?{urlencode({'client_id': client_id, 'redirect_uri': callback_url, 'response_type': 'code', 'scope': 'openid email profile', 'state': state, 'prompt': 'select_account'})}"
    response = RedirectResponse(url=url, status_code=302)
    response.set_cookie("google_oauth_state", state, httponly=True, secure=os.getenv("COOKIE_SECURE", "false").lower() == "true", samesite="lax", max_age=600)
    response.set_cookie("google_oauth_next", "register" if next == "register" else "login", httponly=True, secure=os.getenv("COOKIE_SECURE", "false").lower() == "true", samesite="lax", max_age=600)
    return response


@router.get("/google/callback")
def google_callback(code: str, state: str, request: Request, db: Session = Depends(get_db)):
    expected_state = request.cookies.get("google_oauth_state")
    if not expected_state or not secrets.compare_digest(state, expected_state):
        raise HTTPException(status_code=400, detail="Invalid Google sign-in state")
    client_id, client_secret = os.getenv("GOOGLE_CLIENT_ID"), os.getenv("GOOGLE_CLIENT_SECRET")
    callback_url = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")
    try:
        payload = urlencode({"code": code, "client_id": client_id, "client_secret": client_secret, "redirect_uri": callback_url, "grant_type": "authorization_code"}).encode()
        with urlopen(UrlRequest(GOOGLE_TOKEN_URL, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=10) as result:
            token_data = __import__("json").loads(result.read())
        signing_key = jwt.PyJWKClient("https://www.googleapis.com/oauth2/v3/certs").get_signing_key_from_jwt(token_data["id_token"])
        claims = jwt.decode(
            token_data["id_token"], signing_key.key, algorithms=["RS256"], audience=client_id,
            issuer=["https://accounts.google.com", "accounts.google.com"],
        )
    except Exception as exc:
        logger.exception("Google OAuth exchange or ID-token verification failed")
        debug_detail = "Google sign-in could not be verified"
        if os.getenv("GOOGLE_OAUTH_DEBUG", "false").lower() == "true":
            debug_detail = f"Google sign-in could not be verified ({type(exc).__name__}: {str(exc)[:180]})"
        raise HTTPException(status_code=400, detail=debug_detail) from exc
    if not claims.get("email_verified"):
        raise HTTPException(status_code=400, detail="Google account email could not be verified")
    next_page = request.cookies.get("google_oauth_next", "login")
    user = db.scalar(select(User).where(User.google_subject == claims["sub"]))
    if user is None:
        user = db.scalar(select(User).where(User.email == claims["email"].lower()))
        if user is None:
            if next_page != "register":
                raise HTTPException(status_code=403, detail="Use the email invited by your shop owner to sign in")
            user = User(email=claims["email"].lower(), password_hash=hash_password(secrets.token_urlsafe(48)), role="pending_owner", google_subject=claims["sub"])
            db.add(user)
        else:
            user.google_subject = claims["sub"]
        db.commit()
    user.last_login_at = datetime.utcnow()
    db.commit()
    has_shop = db.scalar(select(BarberShop.id).where(BarberShop.owner_user_id == user.id)) is not None
    destination = "register?google=1" if next_page == "register" and not has_shop else ('admin' if is_platform_admin(user) else 'barber/clients' if user.role == 'barber' else 'dashboard')
    response = RedirectResponse(url=f"{FRONTEND_URL}/{destination}", status_code=302)
    set_login_cookie(response, user)
    response.delete_cookie("google_oauth_state")
    response.delete_cookie("google_oauth_next")
    return response


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"status": "ok"}


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)):
    return public_user(user)
