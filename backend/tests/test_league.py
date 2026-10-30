from collections import Counter

import pytest

from tests.helpers import API, ok


def test_regenerate_after_results_then_delete(api):
    cid = api.create("league", 4, teams=4)
    api.generate(cid)
    api.play_all(cid)
    table = api.standings(cid)
    assert table[0]["points"] >= table[-1]["points"] and sum(r["played"] for r in table) == 12
    assert api.get(cid)["status"] == "completed"
    assert api.c.post(f"{API}/{cid}/fixtures/regenerate").status_code == 400
    ok(api.patch(cid, status="active"))
    ok(api.c.post(f"{API}/{cid}/fixtures/regenerate"))
    assert all(f["status"] == "scheduled" for f in api.fixtures(cid))
    assert all(r["played"] == 0 for r in api.standings(cid))
    api.play_all(cid)
    assert api.c.delete(f"{API}/{cid}").status_code == 204


def test_odd_team_count_completes_and_manual_fixtures_reopen(api):
    cid = api.create("league", 5, teams=5)
    api.generate(cid)
    pending = api.fixtures(cid)
    assert len(pending) == 10
    for f in pending[:-1]:
        ok(api.result(cid, f["id"], 1, 0), 201)
    assert api.get(cid)["status"] == "active"
    ok(api.result(cid, pending[-1]["id"], 1, 0), 201)
    assert api.get(cid)["status"] == "completed"

    t = api.teams(cid)
    manual = ok(api.c.post(f"{API}/{cid}/fixtures/manual",
                           json={"home_team_id": t[0]["id"], "away_team_id": t[1]["id"], "round_number": 99}), 201)
    assert api.get(cid)["status"] == "active"
    assert api.c.delete(f"{API}/{cid}/fixtures/{manual['id']}").status_code == 204
    assert api.get(cid)["status"] == "completed"


def test_status_transitions(api):
    cid = api.create("league", 4, teams=4)
    assert api.patch(cid, status="active").status_code == 400      # no fixtures yet
    assert api.patch(cid, status="completed").status_code == 400
    api.generate(cid)
    assert api.patch(cid, status="draft").status_code == 400       # would unlock team edits
    assert ok(api.patch(cid, name=None))["name"].startswith("league")
    ok(api.patch(cid, description="hello"))
    assert ok(api.patch(cid, description=None))["description"] is None

    ok(api.patch(cid, status="cancelled"))
    f0 = api.fixtures(cid)[0]
    assert api.result(cid, f0["id"], 1, 0).status_code == 400
    assert api.c.post(f"{API}/{cid}/fixtures/regenerate").status_code == 400
    r = api.c.post(f"{API}/{cid}/fixtures/manual", json={
        "home_team_id": f0["home_team_id"], "away_team_id": f0["away_team_id"], "round_number": 9})
    assert r.status_code == 400


def test_team_names(api):
    cid = api.create("league", 4, teams=1)
    r = api.c.post(f"{API}/{cid}/teams/", json={"name": "T0"})
    assert r.status_code == 400 and "already exists" in r.text
    assert api.c.post(f"{API}/{cid}/teams/", json={"name": "   "}).status_code == 400
    assert api.c.post(f"{API}/{cid}/teams/", json={"name": ""}).status_code == 422
    assert api.add_team(cid, "  Lions ")["name"] == "Lions"


# ---- Home and away ----

def _home_away_counts(fixtures):
    home = Counter(f["home_team_id"] for f in fixtures)
    away = Counter(f["away_team_id"] for f in fixtures)
    return home, away


@pytest.mark.parametrize("teams", [2, 3, 4, 5, 6, 8, 11, 20])
def test_single_round_robin_balances_home_and_away(api, teams):
    cid = api.create("league", teams, teams=teams)
    fx = api.generate(cid)
    assert len(fx) == teams * (teams - 1) // 2
    home, away = _home_away_counts(fx)
    for t in api.teams(cid):
        assert abs(home[t["id"]] - away[t["id"]]) <= 1, (t["name"], home[t["id"]], away[t["id"]])


@pytest.mark.parametrize("teams", [4, 5, 20])
def test_home_and_away_league_plays_everyone_twice(api, teams):
    cid = api.create("league", teams, teams=teams, format_config={"two_legged": True})
    assert api.get(cid)["format_config"] == {"two_legged": True}
    fx = api.generate(cid)
    assert len(fx) == teams * (teams - 1)
    # Every ordered pairing once: each pair meets once at each ground
    assert len({(f["home_team_id"], f["away_team_id"]) for f in fx}) == len(fx)
    home, away = _home_away_counts(fx)
    assert set(home.values()) == set(away.values()) == {teams - 1}
    # Second half mirrors the first, so return fixtures come after all first meetings
    rounds = max(f["round_number"] for f in fx)
    first_half = {frozenset((f["home_team_id"], f["away_team_id"])) for f in fx if f["round_number"] <= rounds // 2}
    assert len(first_half) == teams * (teams - 1) // 2

    api.play_all(cid)
    assert api.get(cid)["status"] == "completed"
    assert all(r["played"] == 2 * (teams - 1) for r in api.standings(cid))


def test_league_defaults_to_single_round_robin(api):
    cid = api.create("league", 4, teams=4)
    assert api.get(cid)["format_config"] == {"two_legged": False}
    assert len(api.generate(cid)) == 6
