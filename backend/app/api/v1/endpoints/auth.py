import secrets
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import rate_limit as rl
from app.core.config import settings
from app.core.email import send_email
from app.core.security import get_current_session, get_current_user, hash_code, hash_password, verify_password
from app.db.base import get_db
from app.models.models import AuthSession, Competition, PasswordReset, Standing, User, utcnow
from app.schemas.auth import (
    ChangePasswordRequest, DeleteAccountRequest, ForgotPasswordRequest, LoginRequest, RefreshRequest,
    RegisterRequest, ResetPasswordRequest, TokenResponse, UpdateMeRequest, UserResponse,
)
from app.services.sessions import refresh_session, revoke_all_sessions, revoke_session, start_session

router = APIRouter()


def _username_taken(db: Session, username: str, exclude=None) -> bool:
    query = db.query(User.id).filter(func.lower(User.username) == username.lower())
    if exclude is not None:
        query = query.filter(User.id != exclude)
    return query.first() is not None


# ---------------------------------------------------------------------------
# Signing in and out
# ---------------------------------------------------------------------------

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    ip_key = rl.client_ip(request)
    rl.raise_if_limited((rl.registrations_by_ip, ip_key))
    rl.registrations_by_ip.hit(ip_key)

    # Case-insensitive lookups also catch accounts created before emails were normalised
    if db.query(User).filter(func.lower(User.email) == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if _username_taken(db, payload.username):
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(email=payload.email, username=payload.username, hashed_password=hash_password(payload.password))
    db.add(user)
    db.commit()
    return start_session(db, user, request)


def authenticate(db: Session, request: Request, email: str, password: str) -> TokenResponse:
    """Shared login logic: rate limiting, constant-time failure, session start."""
    email = email.strip().lower()
    email_key, ip_key = email, rl.client_ip(request)
    rl.raise_if_limited((rl.login_failures_by_email, email_key), (rl.login_failures_by_ip, ip_key))

    user = db.query(User).filter(func.lower(User.email) == email).first()
    # verify_password runs even when the user doesn't exist, so timing is the same
    password_ok = verify_password(password, user.hashed_password if user else None)
    if not user or not password_ok or not user.is_active:
        rl.login_failures_by_email.hit(email_key)
        rl.login_failures_by_ip.hit(ip_key)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    rl.login_failures_by_email.reset(email_key)
    return start_session(db, user, request)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    return authenticate(db, request, payload.email, payload.password)


@router.post("/token", response_model=TokenResponse, include_in_schema=False)
def token_form(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Form-data login used by Swagger UI's Authorize button."""
    return authenticate(db, request, form.username, form.password)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    """Swap the refresh token for a new pair. The old refresh token stops working."""
    ip_key = rl.client_ip(request)
    rl.raise_if_limited((rl.refreshes_by_ip, ip_key))
    rl.refreshes_by_ip.hit(ip_key)
    return refresh_session(db, payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """End this device's session; its access and refresh tokens stop working at once."""
    revoke_session(db, session)
    db.commit()


@router.post("/logout-everywhere", status_code=status.HTTP_204_NO_CONTENT)
def logout_everywhere(session: AuthSession = Depends(get_current_session), db: Session = Depends(get_db)):
    """End every session of this account except the one making the request."""
    revoke_all_sessions(db, session.user_id, keep=session.id)
    db.commit()


# ---------------------------------------------------------------------------
# The account
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_me(payload: UpdateMeRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if _username_taken(db, payload.username, exclude=current_user.id):
        raise HTTPException(status_code=400, detail="Username already taken")
    current_user.username = payload.username
    db.commit()
    db.refresh(current_user)
    return current_user


def _check_current_password(user: User, password: str) -> None:
    key = str(user.id)
    rl.raise_if_limited((rl.password_checks_by_user, key))
    if not verify_password(password, user.hashed_password):
        rl.password_checks_by_user.hit(key)
        raise HTTPException(status_code=400, detail="Your current password isn't right")
    rl.password_checks_by_user.reset(key)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    session: AuthSession = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    """Set a new password. Every other device is signed out; this one stays signed in."""
    user = session.user
    _check_current_password(user, payload.current_password)
    user.hashed_password = hash_password(payload.new_password)
    revoke_all_sessions(db, user.id, keep=session.id)
    db.commit()


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    payload: DeleteAccountRequest,
    session: AuthSession = Depends(get_current_session),
    db: Session = Depends(get_db),
):
    """Delete the account and everything it owns. Can't be undone."""
    user = session.user
    _check_current_password(user, payload.password)
    for competition in db.query(Competition).filter(Competition.owner_id == user.id).all():
        # Standings have no ORM relationship to cascade through, so clear them first
        db.query(Standing).filter(Standing.competition_id == competition.id).delete()
        db.delete(competition)
    db.flush()
    db.delete(user)  # sessions and reset codes go with it (ON DELETE CASCADE)
    db.commit()


# ---------------------------------------------------------------------------
# Forgot password
# ---------------------------------------------------------------------------

RESET_ACCEPTED = {"detail": "If that email has an account, we've sent it a code."}


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Email a 6-digit code for resetting the password. The answer is the same
    whether or not the email has an account, so nobody can probe for accounts.
    """
    ip_key = rl.client_ip(request)
    rl.raise_if_limited((rl.reset_requests_by_email, payload.email), (rl.reset_requests_by_ip, ip_key))
    rl.reset_requests_by_email.hit(payload.email)
    rl.reset_requests_by_ip.hit(ip_key)

    user = db.query(User).filter(func.lower(User.email) == payload.email, User.is_active.is_(True)).first()
    if user is None:
        return RESET_ACCEPTED

    now = utcnow()
    # Only the newest code works
    db.query(PasswordReset).filter(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)).update(
        {PasswordReset.used_at: now}, synchronize_session=False
    )
    code = f"{secrets.randbelow(1_000_000):06d}"
    reset = PasswordReset(
        user_id=user.id,
        code_hash="",
        created_at=now,
        expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_CODE_MINUTES),
    )
    db.add(reset)
    db.flush()
    reset.code_hash = hash_code(code, str(reset.id))
    db.commit()

    minutes = settings.PASSWORD_RESET_CODE_MINUTES
    background.add_task(
        send_email,
        user.email,
        f"Your CompApp code: {code}",
        f"Hi {user.username},\n\n"
        f"Your code to reset your CompApp password is:\n\n    {code}\n\n"
        f"It works once and expires in {minutes} minutes.\n\n"
        "If you didn't ask for this, ignore this email. Your password hasn't changed.\n",
    )
    return RESET_ACCEPTED


@router.post("/reset-password", response_model=TokenResponse)
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Set a new password with the emailed code. Signs out every device, then signs this one in."""
    ip_key = rl.client_ip(request)
    rl.raise_if_limited((rl.reset_failures_by_ip, ip_key))
    wrong = HTTPException(status_code=400, detail="That code is wrong or has expired. Ask for a new one.")

    now = utcnow()
    user = db.query(User).filter(func.lower(User.email) == payload.email, User.is_active.is_(True)).first()
    reset = None
    if user is not None:
        reset = (
            db.query(PasswordReset)
            .filter(
                PasswordReset.user_id == user.id,
                PasswordReset.used_at.is_(None),
                PasswordReset.expires_at > now,
                PasswordReset.attempts < settings.PASSWORD_RESET_MAX_ATTEMPTS,
            )
            .order_by(PasswordReset.created_at.desc())
            .first()
        )
    if reset is None or not secrets.compare_digest(reset.code_hash, hash_code(payload.code, str(reset.id))):
        rl.reset_failures_by_ip.hit(ip_key)
        if reset is not None:
            reset.attempts += 1
            db.commit()
        raise wrong

    reset.used_at = now
    user.hashed_password = hash_password(payload.new_password)
    revoke_all_sessions(db, user.id)
    db.commit()
    rl.login_failures_by_email.reset(payload.email)  # a locked-out user can sign in straight away
    return start_session(db, user, request)
