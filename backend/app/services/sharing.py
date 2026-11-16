"""
Share links: a read-only web page for a competition at /c/{code} that anyone
with the link can open, no account needed.

Sharing is separate from "public" (listed in search). A link also works for a
private competition, like an unlisted video. The code is the only secret, so
it's too long to guess. Turning sharing off and on again issues a new code,
which kills the old link.
"""
import re
import secrets

from fastapi import Request

from app.core.config import settings

# 12 URL-safe characters = 72 random bits
CODE_BYTES = 9
CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,32}$")


def new_share_code() -> str:
    return secrets.token_urlsafe(CODE_BYTES)


def share_url(request: Request, code: str) -> str:
    base = settings.PUBLIC_BASE_URL or str(request.base_url)
    return f"{base.rstrip('/')}/c/{code}"
