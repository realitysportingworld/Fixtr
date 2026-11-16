"""Sessions (refresh, sign out), account changes, forgot password, account deletion."""
import re
from datetime import timedelta

import pytest

from app.core import email
from app.core.config import settings
from app.models.models import AuthSession, utcnow
from tests.helpers import API, ok

AUTH = "/api/v1/auth"
PASSWORD = "longenough1"


def register(client, name="sam", password=PASSWORD):
    return ok(client.post(f"{AUTH}/register", json={
        "email": f"{name}@example.com", "username": name, "password": password,
    }), 201)


def login(client, name="sam", password=PASSWORD):
    return client.post(f"{AUTH}/login", json={"email": f"{name}@example.com", "password": password})


def bearer(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def me(client, tokens):
    return client.get(f"{AUTH}/me", headers=bearer(tokens))


def refresh(client, refresh_token):
    return client.post(f"{AUTH}/refresh", json={"refresh_token": refresh_token})


def delete(client, url, **kw):
    return client.request("DELETE", url, **kw)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def test_sign_in_returns_a_short_access_token_and_a_refresh_token(anon):
    tokens = register(anon)
    assert tokens["refresh_token"] and tokens["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert me(anon, tokens).status_code == 200
    assert ok(login(anon))["refresh_token"] != tokens["refresh_token"]  # every sign-in is its own session


def test_refresh_rotates_and_keeps_you_signed_in(anon):
    first = register(anon)
    second = ok(refresh(anon, first["refresh_token"]))
    assert second["refresh_token"] != first["refresh_token"]
    assert me(anon, second).status_code == 200
    third = ok(refresh(anon, second["refresh_token"]))
    assert me(anon, third).status_code == 200


def test_refresh_token_reuse_ends_the_session(anon, monkeypatch):
    first = register(anon)
    second = ok(refresh(anon, first["refresh_token"]))
    # Within the grace period, a retried refresh (lost response) still works...
    retried = ok(refresh(anon, first["refresh_token"]))
    assert me(anon, retried).status_code == 200
    assert refresh(anon, second["refresh_token"]).status_code == 401  # ...and replaces the lost token

    # Later, the old token coming back looks like theft: the whole session ends
    from app.services import sessions
    monkeypatch.setattr(sessions, "ROTATION_GRACE", timedelta(seconds=-1))
    assert refresh(anon, first["refresh_token"]).status_code == 401
    assert refresh(anon, retried["refresh_token"]).status_code == 401
    assert me(anon, retried).status_code == 401


def test_bad_and_expired_refresh_tokens(anon):
    tokens = register(anon)
    assert refresh(anon, "made-up").status_code == 401
    assert refresh(anon, tokens["access_token"][:200]).status_code == 401
    from app.db.base import SessionLocal
    with SessionLocal() as db:
        db.query(AuthSession).update({AuthSession.expires_at: utcnow() - timedelta(seconds=1)})
        db.commit()
    assert refresh(anon, tokens["refresh_token"]).status_code == 401
    assert me(anon, tokens).status_code == 401  # an expired session's access token is dead too


def test_logout_ends_this_session_at_once(anon):
    phone, tablet = register(anon), ok(login(anon))
    assert anon.post(f"{AUTH}/logout", headers=bearer(phone)).status_code == 204
    assert me(anon, phone).status_code == 401                       # access token rejected immediately
    assert refresh(anon, phone["refresh_token"]).status_code == 401
    assert me(anon, tablet).status_code == 200                      # other devices stay signed in


def test_logout_everywhere(anon):
    phone, tablet, laptop = register(anon), ok(login(anon)), ok(login(anon))
    assert anon.post(f"{AUTH}/logout-everywhere", headers=bearer(phone)).status_code == 204
    assert me(anon, phone).status_code == 200
    assert me(anon, tablet).status_code == 401 and me(anon, laptop).status_code == 401


# ---------------------------------------------------------------------------
# Account changes
# ---------------------------------------------------------------------------

def test_change_username(anon):
    tokens = register(anon)
    register(anon, "taken")
    url, h = f"{AUTH}/me", bearer(tokens)
    assert ok(anon.patch(url, json={"username": "  Samuel "}, headers=h))["username"] == "Samuel"
    assert anon.patch(url, json={"username": "TAKEN"}, headers=h).status_code == 400
    assert anon.patch(url, json={"username": "no spaces"}, headers=h).status_code == 422
    assert ok(anon.patch(url, json={"username": "samuel"}, headers=h))["username"] == "samuel"  # own name, new case


def test_change_password_signs_out_other_devices(anon):
    phone, tablet = register(anon), ok(login(anon))
    url = f"{AUTH}/change-password"
    r = anon.post(url, json={"current_password": "wrongwrong", "new_password": "brand-new-pw"}, headers=bearer(phone))
    assert r.status_code == 400 and "current password" in r.json()["detail"]
    assert anon.post(url, json={"current_password": PASSWORD, "new_password": "short"}, headers=bearer(phone)).status_code == 422

    assert anon.post(url, json={"current_password": PASSWORD, "new_password": "brand-new-pw"},
                     headers=bearer(phone)).status_code == 204
    assert me(anon, phone).status_code == 200 and me(anon, tablet).status_code == 401
    assert login(anon).status_code == 401
    ok(login(anon, password="brand-new-pw"))


def test_wrong_current_password_is_rate_limited(anon):
    tokens = register(anon)
    body = {"current_password": "wrongwrong", "new_password": "brand-new-pw"}
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        assert anon.post(f"{AUTH}/change-password", json=body, headers=bearer(tokens)).status_code == 400
    assert anon.post(f"{AUTH}/change-password", json={**body, "current_password": PASSWORD},
                     headers=bearer(tokens)).status_code == 429


# ---------------------------------------------------------------------------
# Forgot password
# ---------------------------------------------------------------------------

def emailed_code() -> str:
    assert email.outbox, "no email was sent"
    return re.search(r"\b(\d{6})\b", email.outbox[-1].get_content()).group(1)


def forgot(client, name="sam"):
    return client.post(f"{AUTH}/forgot-password", json={"email": f"{name}@example.com"})


def reset(client, code, name="sam", password="fresh-password"):
    return client.post(f"{AUTH}/reset-password", json={
        "email": f"{name}@example.com", "code": code, "new_password": password,
    })


def test_forgot_password_end_to_end(anon):
    old = register(anon)
    assert forgot(anon).status_code == 202
    msg = email.outbox[-1]
    assert msg["To"] == "sam@example.com" and "code" in msg["Subject"]
    tokens = ok(reset(anon, f" {emailed_code()} "))  # spaces from copy-paste are fine
    assert me(anon, tokens).status_code == 200                       # signed straight in
    assert me(anon, old).status_code == 401                          # every old session ended
    assert login(anon).status_code == 401
    ok(login(anon, password="fresh-password"))


def test_forgot_password_does_not_reveal_accounts(anon):
    register(anon)
    known, unknown = forgot(anon), forgot(anon, "nobody")
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(email.outbox) == 1  # only the real account got mail


def test_reset_code_is_single_use_and_newest_only(anon):
    register(anon)
    forgot(anon)
    first = emailed_code()
    forgot(anon)
    second = emailed_code()
    if first != second:
        assert reset(anon, first).status_code == 400   # replaced by the newer code
    ok(reset(anon, second))
    assert reset(anon, second, password="another-password").status_code == 400  # used up


def test_reset_code_dies_after_too_many_wrong_tries(anon):
    register(anon)
    forgot(anon)
    code = emailed_code()
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(settings.PASSWORD_RESET_MAX_ATTEMPTS):
        assert reset(anon, wrong).status_code == 400
    assert reset(anon, code).status_code == 400  # even the right code no longer works


def test_reset_code_expires(anon):
    register(anon)
    forgot(anon)
    code = emailed_code()
    from app.db.base import SessionLocal
    from app.models.models import PasswordReset
    with SessionLocal() as db:
        db.query(PasswordReset).update({PasswordReset.expires_at: utcnow() - timedelta(seconds=1)})
        db.commit()
    assert reset(anon, code).status_code == 400


def test_reset_validation_and_unknown_email(anon):
    register(anon)
    forgot(anon)
    assert reset(anon, "12345").status_code == 422
    assert reset(anon, "abcdef").status_code == 422
    assert reset(anon, emailed_code(), password="short").status_code == 422
    assert reset(anon, "123456", name="nobody").status_code == 400


def test_forgot_password_is_rate_limited(anon):
    register(anon)
    codes = [forgot(anon).status_code for _ in range(4)]
    assert codes == [202, 202, 202, 429]
    assert len(email.outbox) == 3


def test_reset_unlocks_a_locked_out_account(anon):
    register(anon)
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        login(anon, password="wrongwrong")
    assert login(anon).status_code == 429
    forgot(anon)
    ok(reset(anon, emailed_code()))
    ok(login(anon, password="fresh-password"))


# ---------------------------------------------------------------------------
# Deleting the account
# ---------------------------------------------------------------------------

def test_delete_account_removes_everything(anon, other):
    tokens = register(anon)
    h = bearer(tokens)
    cid = ok(anon.post(f"{API}/", json={"name": "Mine", "format": "league", "sport": "football",
                                        "max_participants": 2, "is_public": True}, headers=h), 201)["id"]
    teams = [ok(anon.post(f"{API}/{cid}/teams/", json={"name": n}, headers=h), 201) for n in ("A", "B")]
    pid = ok(anon.post(f"{API}/{cid}/teams/{teams[0]['id']}/players/", json={"name": "P"}, headers=h), 201)["id"]
    f = ok(anon.post(f"{API}/{cid}/fixtures/generate", headers=h), 201)[0]
    side = "home_score" if f["home_team_id"] == teams[0]["id"] else "away_score"
    ok(anon.post(f"{API}/{cid}/fixtures/{f['id']}/result", headers=h, json={
        "home_score": 0, "away_score": 0, side: 1, "events": [{"type": "goal", "player_id": pid}],
    }), 201)
    ok(anon.post(f"{API}/{cid}/share", headers=h))

    assert delete(anon, f"{AUTH}/me", json={"password": "wrongwrong"}, headers=h).status_code == 400
    assert delete(anon, f"{AUTH}/me", json={"password": PASSWORD}, headers=h).status_code == 204

    assert me(anon, tokens).status_code == 401
    assert login(anon).status_code == 401
    assert other.c.get(f"{API}/{cid}").status_code == 404
    register(anon)  # the email and username are free again


@pytest.mark.parametrize("path", ["/me", "/logout", "/logout-everywhere", "/change-password"])
def test_account_endpoints_need_a_session(anon, path):
    method = "get" if path == "/me" else "post"
    assert getattr(anon, method)(f"{AUTH}{path}").status_code == 401


def test_health_checks_the_database(anon):
    assert ok(anon.get("/health")) == {"status": "ok", "database": "ok"}
