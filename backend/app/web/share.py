"""
The shared competition page: /c/{code}, server-rendered HTML that opens
straight from a WhatsApp (or any) link with no app or account. Open Graph
tags give the chat a title and a one-line summary.

Pages carry a strict Content-Security-Policy (no outside resources; the one
style block and script are allowed by a per-response nonce), never send a
Referer (the URL is the secret), and stay out of search engines unless the
competition is public.
"""
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.db.base import get_db
from app.models.models import Competition
from app.services.share_view import build_share_view
from app.services.sharing import CODE_PATTERN, share_url

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

CACHE_SECONDS = 30  # short, so new results and a revoked link show up quickly


def _headers(nonce: str, indexable: bool, cacheable: bool) -> dict:
    return {
        "Content-Security-Policy": (
            "default-src 'none'; "
            f"style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; "
            "img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        ),
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "X-Robots-Tag": "all" if indexable else "noindex, nofollow",
        # Unlisted pages may only sit in the reader's own browser cache, not a shared one
        "Cache-Control": (f"{'public' if indexable else 'private'}, max-age={CACHE_SECONDS}"
                          if cacheable else "no-store"),
    }


@router.api_route("/c/{code}", methods=["GET", "HEAD"], response_class=HTMLResponse)
def shared_competition(code: str, request: Request, db: Session = Depends(get_db)):
    nonce = secrets.token_urlsafe(16)
    competition = None
    if CODE_PATTERN.match(code):  # don't query the database for junk
        competition = (
            db.query(Competition)
            .options(joinedload(Competition.owner))
            .filter(Competition.share_code == code)
            .first()
        )
    if competition is None:
        return templates.TemplateResponse(
            request, "not_found.html", {"nonce": nonce}, status_code=404,
            headers=_headers(nonce, indexable=False, cacheable=False),
        )

    now = datetime.now(timezone.utc)
    return templates.TemplateResponse(
        request,
        "share.html",
        {
            "c": build_share_view(db, competition),
            "nonce": nonce,
            "canonical_url": share_url(request, code),
            "generated_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "generated_at_text": f"{now:%H:%M} UTC",
        },
        headers=_headers(nonce, indexable=competition.is_public, cacheable=True),
    )
