from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from pydantic import ValidationError

from app.core import rate_limit
from app.core.config import Settings, settings
from tests.helpers import API, ok

AUTH = "/api/v1/auth"


def register(client, email, username, password):
    return client.post(f"{AUTH}/register", json={"email": email, "username": username, "password": password})


def test_weak_secret_key_refused():
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(SECRET_KEY="short", DATABASE_URL="sqlite://")


def test_registration_validation_and_email_normalisation(anon):
    assert register(anon, "s1@x.co", "sec1", "short").status_code == 422
    assert register(anon, "s1@x.co", "sec1", "é" * 40).status_code == 422       # 80 bytes > bcrypt limit
    assert register(anon, "s1@x.co", "a b", "longenough1").status_code == 422
    assert register(anon, "s1@x.co", "ab", "longenough1").status_code == 422
    assert register(anon, "s1@x.co", "sec1", "        ").status_code == 422
    ok(register(anon, "  Mixed@Case.CO ", "Sec1", "longenough1"), 201)
    assert register(anon, "mixed@case.co", "other", "longenough1").status_code == 400  # same email
    assert register(anon, "new@case.co", "SEC1", "longenough1").status_code == 400     # same username

    token = ok(anon.post(f"{AUTH}/login", json={"email": "MIXED@case.co", "password": "longenough1"}))["access_token"]
    me = ok(anon.get(f"{AUTH}/me", headers={"Authorization": f"Bearer {token}"}))
    assert me["email"] == "mixed@case.co"
    ok(anon.post(f"{AUTH}/token", data={"username": "mixed@case.co", "password": "longenough1"}))  # Swagger form


def test_login_rate_limiting(anon):
    ok(register(anon, "who@x.co", "who", "longenough1"), 201)
    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        assert anon.post(f"{AUTH}/login", json={"email": "who@x.co", "password": "wrongwrong"}).status_code == 401
    r = anon.post(f"{AUTH}/login", json={"email": "who@x.co", "password": "longenough1"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0          # locked even with right password
    # Unknown emails fail the same way (no enumeration)
    assert anon.post(f"{AUTH}/login", json={"email": "nobody@x.co", "password": "whatever1"}).status_code == 401
    rate_limit.login_failures_by_email.reset("who@x.co")
    ok(anon.post(f"{AUTH}/login", json={"email": "who@x.co", "password": "longenough1"}))

    # IP-wide limit
    for i in range(settings.LOGIN_MAX_ATTEMPTS * 4):
        anon.post(f"{AUTH}/login", json={"email": f"spray{i}@x.co", "password": "wrongwrong"})
    assert anon.post(f"{AUTH}/login", json={"email": "who@x.co", "password": "longenough1"}).status_code == 429


def test_token_validation(anon):
    token = ok(register(anon, "tok@x.co", "tok", "longenough1"), 201)["access_token"]
    uid = ok(anon.get(f"{AUTH}/me", headers={"Authorization": f"Bearer {token}"}))["id"]

    def status_with(payload, key=settings.SECRET_KEY, alg="HS256", raw=None):
        tok = raw or pyjwt.encode(payload, key, algorithm=alg)
        return anon.get(f"{AUTH}/me", headers={"Authorization": f"Bearer {tok}"}).status_code

    future = datetime.now(timezone.utc) + timedelta(hours=1)
    assert status_with({"sub": uid, "exp": future}) == 200
    assert status_with({"sub": uid, "exp": future}, key="x" * 40) == 401                   # wrong key
    assert status_with({"sub": uid}) == 401                                                 # no exp
    assert status_with({"sub": uid, "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}) == 401
    assert status_with({"sub": "not-a-uuid", "exp": future}) == 401
    assert status_with({"sub": uid, "exp": future}, key=None, alg="none") == 401            # alg=none
    assert status_with(None, raw="garbage") == 401


def test_cors_and_docs_hidden(anon):
    r = anon.options(f"{API}/", headers={"Origin": "http://localhost:8081", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:8081"
    assert "access-control-allow-credentials" not in r.headers
    r = anon.options(f"{API}/", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers
    assert anon.get("/docs").status_code == 404 and anon.get("/openapi.json").status_code == 404


def test_size_limits(api):
    base = {"format": "league", "sport": "football"}
    assert api.c.post(f"{API}/", json={**base, "name": "x", "max_participants": 513}).status_code == 422
    assert api.c.post(f"{API}/", json={**base, "name": "x" * 101, "max_participants": 4}).status_code == 422
    assert api.c.post(f"{API}/", json={**base, "name": "x", "max_participants": 4,
                                       "scoring_config": {"junk": "y" * 3000}}).status_code == 422
    cid = api.create("league", 2, teams=2)
    f = api.generate(cid)[0]
    url = f"{API}/{cid}/fixtures/{f['id']}/result"
    assert api.c.post(url, json={"home_score": 10**10, "away_score": 0}).status_code == 422
    assert api.c.post(url, json={"home_score": 1, "away_score": 0, "extra_data": {"x": "y" * 20000}}).status_code == 422
    assert api.c.post(f"{API}/{cid}/teams/", json={"name": "n" * 101}).status_code == 422


def test_registration_rate_limit_per_ip(anon):
    codes = [register(anon, f"bulk{i}@x.co", f"bulk{i}", "longenough1").status_code for i in range(11)]
    assert codes[:10] == [201] * 10 and codes[10] == 429
