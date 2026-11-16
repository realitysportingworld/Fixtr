"""
Signed-in sessions: issuing, rotating and revoking refresh tokens.

A refresh token is good for REFRESH_TOKEN_EXPIRE_DAYS after its last use and
is replaced on every refresh. If the previous token turns up again after the
grace period, someone else has a copy, so the whole session is ended and
both copies stop working.
"""
from datetime import timedelta
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_token, new_refresh_token
from app.models.models import AuthSession, User, utcnow
from app.schemas.auth import TokenResponse

# A retry of a refresh whose response was lost (flaky mobile network) may
# present the previous token; within this window it's honoured, not treated as theft
ROTATION_GRACE = timedelta(seconds=30)

_invalid = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Your session has ended. Please sign in again.",
)


def _tokens(session: AuthSession, refresh_token: str) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(session.user_id, session.id),
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def _user_agent(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    agent = request.headers.get("user-agent")
    return agent[:200] if agent else None


def start_session(db: Session, user: User, request: Optional[Request] = None) -> TokenResponse:
    """Sign a device in. Commits."""
    refresh_token = new_refresh_token()
    now = utcnow()
    # Tidy up this user's dead sessions while we're here
    db.query(AuthSession).filter(
        AuthSession.user_id == user.id,
        (AuthSession.expires_at < now) | (AuthSession.revoked_at < now - timedelta(days=7)),
    ).delete(synchronize_session=False)
    session = AuthSession(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        user_agent=_user_agent(request),
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(session)
    db.commit()
    return _tokens(session, refresh_token)


def refresh_session(db: Session, refresh_token: str) -> TokenResponse:
    """Swap a refresh token for a new access and refresh token. Commits."""
    now = utcnow()
    presented = hash_token(refresh_token)
    session = db.query(AuthSession).filter(AuthSession.token_hash == presented).first()
    reused = False
    if session is None:
        session = db.query(AuthSession).filter(AuthSession.previous_token_hash == presented).first()
        if session is None:
            raise _invalid
        reused = True

    if session.revoked_at is not None or session.expires_at <= now or not session.user.is_active:
        raise _invalid
    if reused and (session.rotated_at is None or now - session.rotated_at > ROTATION_GRACE):
        session.revoked_at = now  # a replaced token came back: assume it was stolen
        db.commit()
        raise _invalid

    new_token = new_refresh_token()
    if not reused:
        session.previous_token_hash = presented
    session.token_hash = hash_token(new_token)
    session.rotated_at = now
    session.last_used_at = now
    session.expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    db.commit()
    return _tokens(session, new_token)


def revoke_session(db: Session, session: AuthSession) -> None:
    """Does NOT commit."""
    if session.revoked_at is None:
        session.revoked_at = utcnow()


def revoke_all_sessions(db: Session, user_id: UUID, keep: Optional[UUID] = None) -> int:
    """End every session of a user (but `keep`). Does NOT commit. Returns how many ended."""
    query = db.query(AuthSession).filter(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    if keep is not None:
        query = query.filter(AuthSession.id != keep)
    return query.update({AuthSession.revoked_at: utcnow()}, synchronize_session=False)
