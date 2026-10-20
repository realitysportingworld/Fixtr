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


def create_access_token(data: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = data.copy()
    payload["iat"] = now
    payload["exp"] = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    from app.models.models import User

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        user_id = UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, TypeError):
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_exception

    return user
