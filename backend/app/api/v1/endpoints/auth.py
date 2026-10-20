from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.rate_limit import (
    client_ip, login_failures_by_email, login_failures_by_ip, raise_if_limited, registrations_by_ip,
)
from app.core.security import hash_password, verify_password, create_access_token, get_current_user
from app.db.base import get_db
from app.models.models import User
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserResponse

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    ip_key = client_ip(request)
    raise_if_limited((registrations_by_ip, ip_key))
    registrations_by_ip.hit(ip_key)

    # Case-insensitive lookups also catch accounts created before emails were normalised
    if db.query(User).filter(func.lower(User.email) == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if db.query(User).filter(func.lower(User.username) == payload.username.lower()).first():
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)


def authenticate(db: Session, request: Request, email: str, password: str) -> TokenResponse:
    """Shared login logic: rate limiting, constant-time failure, token issue."""
    email = email.strip().lower()
    email_key, ip_key = email, client_ip(request)
    raise_if_limited((login_failures_by_email, email_key), (login_failures_by_ip, ip_key))

    user = db.query(User).filter(func.lower(User.email) == email).first()
    # verify_password runs even when the user doesn't exist, so timing is the same
    password_ok = verify_password(password, user.hashed_password if user else None)
    if not user or not password_ok or not user.is_active:
        login_failures_by_email.hit(email_key)
        login_failures_by_ip.hit(ip_key)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    login_failures_by_email.reset(email_key)
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    return authenticate(db, request, payload.email, payload.password)


@router.post("/token", response_model=TokenResponse, include_in_schema=False)
def token_form(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Form-data login used by Swagger UI's Authorize button."""
    return authenticate(db, request, form.username, form.password)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user
