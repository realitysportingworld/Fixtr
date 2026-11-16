import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.base import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

# bcrypt only uses the first 72 bytes and bcrypt>=5 raises on longer input
BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


# Checked against when the email doesn't exist, so a failed login takes the
# same time whether or not the account exists (prevents email enumeration).
_DUMMY_HASH = hash_password("dummy-password-for-timing")


def verify_password(plain: str, hashed: str | None) -> bool:
    candidate = plain.encode("utf-8")
    if len(candidate) > BCRYPT_MAX_BYTES:
        bcrypt.checkpw(b"x", _DUMMY_HASH.encode("utf-8"))
        return False
    if hashed is None:
        bcrypt.checkpw(candidate, _DUMMY_HASH.encode("utf-8"))
        return False
    return bcrypt.checkpw(candidate, hashed.encode("utf-8"))


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Refresh tokens are long and random, so a plain SHA-256 is enough to store them."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_code(code: str, salt: str) -> str:
    """Short codes (6 digits) are keyed with SECRET_KEY so a leaked table can't be brute-forced offline."""
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), f"{salt}:{code}".encode("utf-8"), hashlib.sha256).hexdigest()


def create_access_token(user_id: UUID, session_id: UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_session(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """
    The signed-in session behind the request's access token. The session is
    checked on every request, so signing out or revoking takes effect at once,
    not when the token expires.
    """
    from app.models.models import AuthSession, User, utcnow

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "sub", "sid"]},
        )
        if payload.get("typ") != "access":
            raise ValueError("not an access token")
        user_id, session_id = UUID(payload["sub"]), UUID(payload["sid"])
    except (jwt.PyJWTError, ValueError, TypeError):
        raise _credentials_exception

    session = (
        db.query(AuthSession)
        .join(User, AuthSession.user_id == User.id)
        .filter(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > utcnow(),
            User.is_active.is_(True),
        )
        .first()
    )
    if session is None:
        raise _credentials_exception
    return session


def get_current_user(session=Depends(get_current_session)):
    return session.user
