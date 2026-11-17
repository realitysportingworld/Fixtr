import re

import pytest

from tests.helpers import ok


def path_of(url: str) -> str:
    return "/" + url.split("/", 3)[3]


@pytest.fixture
def league(api):
    cid = api.create("league", 4)
    for n in ("Arsenal", "Brentford", "Chelsea", "Dulwich"):
        api.add_team(cid, n)
    api.generate(cid)
    return cid


def test_link_is_off_until_turned_on(api, league):
    assert api.get(league)["share_url"] is None
    url = api.share(league)
    assert re.fullmatch(r"http://testserver/c/[A-Za-z0-9_-]{12}", url)
    assert api.share(league) == url                       # asking again keeps the same link
    assert api.get(league)["share_url"] == url
    assert ok(api.c.get("/api/v1/competitions/"))[0]["share_url"] == url


def test_public_base_url_setting(api, league, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://fixtr.example.com/")
    assert api.share(league).startswith("https://fixtr.example.com/c/")


def test_page_opens_without_an_account(api, anon, league):
    url = api.share(league)
    r = anon.get(path_of(url))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    html = r.text
    assert "<h1>" in html and "Arsenal" in html and "Round 1" in html
    # Link preview for WhatsApp and friends
    assert 'property="og:title"' in html and f'content="{url}"' in html
    assert "Football · League · 4 teams" in html


def test_page_shows_results_table_and_scorers(api, anon, league):
    api.play_all(league, 2, 1)
    teams = {t["name"]: t["id"] for t in api.teams(league)}
    pid = ok(api.add_player(league, teams["Arsenal"], "Saka", 7), 201)["id"]
    f = next(f for f in api.fixtures(league) if teams["Arsenal"] in (f["home_team_id"], f["away_team_id"]))
    side = "home" if f["home_team_id"] == teams["Arsenal"] else "away"
    ok(api.result(league, f["id"], 2 if side == "home" else 1, 1 if side == "home" else 2, method="put",
                  events=[{"type": "goal", "player_id": pid}]))
    html = anon.get(path_of(api.share(league))).text
    assert "2–1" in html
    assert 'id="table"' in html and 'id="scorers"' in html and "Saka" in html
    assert "Champions:" in html  # finished league: the preview names the winner


def test_knockout_page_shows_bracket_and_winner(api, anon):
    cid = api.create("knockout", 4, teams=4)
    api.generate(cid)
    api.play_knockout_to_end(cid)
    html = anon.get(path_of(api.share(cid))).text
    assert 'id="bracket"' in html and "Semi-Final" in html and "Final" in html
    assert "Winner:" in html


def test_two_legged_ties_show_aggregate(api, anon):
    cid = api.create("knockout", 4, teams=4, format_config={"two_legged": True})
    api.generate(cid)
    for f in sorted(api.fixtures(cid), key=lambda f: f["leg"] or 0):
        ok(api.result(cid, f["id"], 2, 1, tiebreak="home"), 201)
    html = anon.get(path_of(api.share(cid))).text
    assert "Aggregate 3–3" in html and "won the tiebreak" in html


def test_group_knockout_and_draft_pages(api, anon):
    cid = api.create("group_knockout", 8, teams=8, num_groups=2)
    api.generate(cid)
    html = anon.get(path_of(api.share(cid))).text
    assert "Group A" in html and "Group B" in html

    draft = api.create("league", 4, teams=2)
    html = anon.get(path_of(api.share(draft))).text
    assert "been drawn yet" in html and "T0" in html


def test_kickoff_times_are_in_the_page(api, anon, league):
    f = api.fixtures(league)[0]
    ok(api.schedule(league, [{"fixture_id": f["id"], "scheduled_at": "2026-11-07T15:00:00Z"}]))
    html = anon.get(path_of(api.share(league))).text
    assert '<time datetime="2026-11-07T15:00:00Z" data-local>Sat 7 Nov · 15:00 UTC</time>' in html


def test_turning_the_link_off_kills_it_and_a_new_one_is_different(api, anon, league):
    old = api.share(league)
    assert api.unshare(league).status_code == 204
    assert api.get(league)["share_url"] is None
    r = anon.get(path_of(old))
    assert r.status_code == 404 and "isn't working" in r.text
    assert r.headers["cache-control"] == "no-store"
    new = api.share(league)
    assert new != old and anon.get(path_of(new)).status_code == 200


def test_unknown_and_junk_codes_are_404(anon):
    for code in ("doesnotexist12", "x", "a" * 40, "bad%20code!!", "..%2f..%2fetc"):
        assert anon.get(f"/c/{code}").status_code == 404


def test_only_the_owner_can_share_or_see_the_link(api, other, league):
    assert other.c.post(f"/api/v1/competitions/{league}/share").status_code == 404
    assert other.unshare(league).status_code == 404
    api.share(league)
    ok(api.patch(league, is_public=True))
    assert other.get(league)["share_url"] is None  # viewers of a public competition don't get it
    found = ok(other.c.get("/api/v1/competitions/public"))
    assert all(c["share_url"] is None for c in found)


def test_names_are_escaped(api, anon):
    cid = api.create("league", 2)
    api.add_team(cid, '<script>alert("x")</script>')
    api.add_team(cid, "Fine")
    ok(api.patch(cid, name='Cup "</title><script>bad()</script>'))
    api.generate(cid)
    html = anon.get(path_of(api.share(cid))).text
    assert "<script>alert" not in html and "<script>bad" not in html
    assert "&lt;script&gt;alert(&#34;x&#34;)&lt;/script&gt;" in html


def test_security_headers(api, anon, league):
    r = anon.get(path_of(api.share(league)))
    h = r.headers
    csp = h["content-security-policy"]
    nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
    assert "default-src 'none'" in csp and "frame-ancestors 'none'" in csp
    assert f'<style nonce="{nonce}">' in r.text and f'<script nonce="{nonce}">' in r.text
    assert not re.search(r'\sstyle="', r.text)  # inline style attributes would be blocked
    assert h["referrer-policy"] == "no-referrer"
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-robots-tag"] == "noindex, nofollow"
    assert h["cache-control"] == "private, max-age=30"
    # A fresh nonce every time
    assert re.search(r"'nonce-([^']+)'", anon.get(path_of(api.share(league))).headers["content-security-policy"]).group(1) != nonce


def test_public_competitions_may_be_indexed(api, anon, league):
    url = api.share(league)
    ok(api.patch(league, is_public=True))
    h = anon.get(path_of(url)).headers
    assert h["x-robots-tag"] == "all" and h["cache-control"] == "public, max-age=30"


def test_head_requests_for_link_previews(api, anon, league):
    r = anon.head(path_of(api.share(league)))
    assert r.status_code == 200 and r.content == b""


def test_share_page_is_not_in_the_api_schema(api):
    from app.main import app
    assert not any(p.startswith("/c/") for p in app.openapi()["paths"])
