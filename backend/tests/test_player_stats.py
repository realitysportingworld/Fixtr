import pytest

from tests.helpers import ok


@pytest.fixture
def match(api):
    """A two-team football league with squads, and its one fixture."""
    cid = api.create("league", 2)
    home = api.add_team(cid, "Reds")
    away = api.add_team(cid, "Blues")
    fixture = api.generate(cid)[0]
    if fixture["home_team_id"] != home["id"]:
        home, away = away, home
    squad = {}
    for team, names in ((home, ["Ade", "Bola", "Chi"]), (away, ["Dan", "Eze"])):
        for i, n in enumerate(names, start=1):
            squad[n] = ok(api.add_player(cid, team["id"], n, i), 201)["id"]
    return {"cid": cid, "fid": fixture["id"], "home": home, "away": away, "p": squad}


def goal(pid, assist=None, minute=None, kind="goal"):
    return {"type": kind, "player_id": pid, "assist_player_id": assist, "minute": minute}


# ---------------------------------------------------------------------------
# Squads
# ---------------------------------------------------------------------------

def test_squad_is_listed_by_shirt_number(api, match):
    cid, home = match["cid"], match["home"]["id"]
    ok(api.add_player(cid, home, "No Number"), 201)
    names = [p["name"] for p in api.players(cid, home)]
    assert names == ["Ade", "Bola", "Chi", "No Number"]


def test_squad_names_and_numbers_are_unique_per_team(api, match):
    cid, home, away = match["cid"], match["home"]["id"], match["away"]["id"]
    assert api.add_player(cid, home, "  ade ").status_code == 400      # same name, any case/spacing
    assert api.add_player(cid, home, "Zed", 1).status_code == 400      # number taken
    ok(api.add_player(cid, away, "Ade", 3), 201)                       # fine in the other team
    assert api.add_player(cid, home, "   ").status_code == 422


def test_rename_and_renumber(api, match):
    cid, home, p = match["cid"], match["home"]["id"], match["p"]
    url = f"/api/v1/competitions/{cid}/teams/{home}/players/{p['Ade']}"
    assert ok(api.c.patch(url, json={"name": "Adeola", "shirt_number": 9}))["shirt_number"] == 9
    assert ok(api.c.patch(url, json={"shirt_number": None}))["shirt_number"] is None
    assert api.c.patch(url, json={"name": "Bola"}).status_code == 400


def test_player_from_another_team_or_competition_is_404(api, match):
    cid, home, away, p = match["cid"], match["home"]["id"], match["away"]["id"], match["p"]
    assert api.c.delete(f"/api/v1/competitions/{cid}/teams/{away}/players/{p['Ade']}").status_code == 404
    other = api.create("league", 2, teams=2)
    assert api.c.get(f"/api/v1/competitions/{other}/teams/{home}/players/").status_code == 404


def test_only_the_owner_edits_squads(other, match):
    cid, home = match["cid"], match["home"]["id"]
    assert other.add_player(cid, home, "Sneaky").status_code == 404


def test_player_with_stats_cannot_be_removed(api, match):
    cid, fid, home, p = match["cid"], match["fid"], match["home"]["id"], match["p"]
    ok(api.result(cid, fid, 1, 0, events=[goal(p["Ade"], assist=p["Bola"])]), 201)
    for name in ("Ade", "Bola"):  # scorer and assister
        r = api.c.delete(f"/api/v1/competitions/{cid}/teams/{home}/players/{p[name]}")
        assert r.status_code == 400 and "recorded" in r.json()["detail"]
    assert api.c.delete(f"/api/v1/competitions/{cid}/teams/{home}/players/{p['Chi']}").status_code == 204


# ---------------------------------------------------------------------------
# Match events
# ---------------------------------------------------------------------------

def test_events_are_saved_with_the_result_in_match_order(api, match):
    cid, fid, p = match["cid"], match["fid"], match["p"]
    events = [
        goal(p["Dan"], minute=70),
        goal(p["Ade"], assist=p["Bola"], minute=12),
        {"type": "yellow_card", "player_id": p["Eze"], "minute": 30},
        goal(p["Chi"]),  # no minute: listed last
    ]
    ok(api.result(cid, fid, 2, 1, events=events), 201)
    saved = api.events(cid, fid)
    assert [(e["player_id"], e["minute"]) for e in saved] == [
        (p["Ade"], 12), (p["Eze"], 30), (p["Dan"], 70), (p["Chi"], None),
    ]
    assert saved[0]["assist_player_id"] == p["Bola"]


def test_more_goals_than_the_score_is_rejected(api, match):
    cid, fid, p = match["cid"], match["fid"], match["p"]
    r = api.result(cid, fid, 1, 0, events=[goal(p["Ade"]), goal(p["Bola"])])
    home = match["home"]["name"]
    assert r.status_code == 400 and f"{home} scored 1, but 2 goals" in r.json()["detail"]
    assert api.fixtures(cid)[0]["status"] == "scheduled"  # nothing saved


def test_own_goal_counts_for_the_other_side(api, match):
    cid, fid, p = match["cid"], match["fid"], match["p"]
    # A Blues own goal is a Reds goal, so 0-1 can't have it
    r = api.result(cid, fid, 0, 1, events=[goal(p["Dan"], kind="own_goal")])
    assert r.status_code == 400
    ok(api.result(cid, fid, 1, 0, events=[goal(p["Dan"], kind="own_goal")]), 201)
    stats = api.stats(cid)
    assert stats["scorers"] == []  # own goals don't count as the player's goals


def test_partial_scorers_are_fine(api, match):
    cid, fid, p = match["cid"], match["fid"], match["p"]
    ok(api.result(cid, fid, 3, 2, events=[goal(p["Ade"])]), 201)


@pytest.mark.parametrize("bad, message", [
    ("stranger", "squads"),
    ("cross_assist", "team-mate"),
    ("self_assist", "own goal"),
    ("card_assist", "Only a goal"),
    ("three_yellows", "two yellow"),
    ("two_reds", "sent off once"),
])
def test_invalid_events_are_rejected(api, match, bad, message):
    cid, fid, p = match["cid"], match["fid"], match["p"]
    other = api.create("league", 2, teams=2)
    stranger = ok(api.add_player(other, api.teams(other)[0]["id"], "Stranger"), 201)["id"]
    events = {
        "stranger": [goal(stranger)],
        "cross_assist": [goal(p["Ade"], assist=p["Dan"])],
        "self_assist": [goal(p["Ade"], assist=p["Ade"])],
        "card_assist": [{"type": "red_card", "player_id": p["Ade"], "assist_player_id": p["Bola"]}],
        "three_yellows": [{"type": "yellow_card", "player_id": p["Ade"]}] * 3,
        "two_reds": [{"type": "red_card", "player_id": p["Ade"]}] * 2,
    }[bad]
    r = api.result(cid, fid, 1, 1, events=events)
    assert r.status_code in (400, 422)
    assert message in r.text


def test_update_replaces_or_keeps_events(api, match):
    cid, fid, p = match["cid"], match["fid"], match["p"]
    ok(api.result(cid, fid, 2, 0, events=[goal(p["Ade"]), goal(p["Bola"])]), 201)

    ok(api.result(cid, fid, 3, 0, method="put"))  # events left out: kept
    assert len(api.events(cid, fid)) == 2

    # Lowering the score below the recorded goals needs the scorers fixed too
    r = api.result(cid, fid, 1, 0, method="put")
    assert r.status_code == 400 and "Fix the scorers or the score" in r.json()["detail"]
    ok(api.result(cid, fid, 1, 0, method="put", events=[goal(p["Chi"])]))
    assert [e["player_id"] for e in api.events(cid, fid)] == [p["Chi"]]

    ok(api.result(cid, fid, 1, 0, method="put", events=[]))  # [] clears them
    assert api.events(cid, fid) == []


def test_clearing_the_result_removes_its_events(api, match):
    cid, fid, p = match["cid"], match["fid"], match["p"]
    ok(api.result(cid, fid, 1, 0, events=[goal(p["Ade"])]), 201)
    assert api.clear(cid, fid).status_code == 204
    assert api.events(cid, fid) == []
    assert api.stats(cid)["scorers"] == []


def test_regenerating_fixtures_removes_events(api):
    cid = api.create("league", 4, teams=4)
    f = api.generate(cid)[0]
    pid = ok(api.add_player(cid, f["home_team_id"], "Ade"), 201)["id"]
    ok(api.result(cid, f["id"], 1, 0, events=[goal(pid)]), 201)
    assert len(api.stats(cid)["scorers"]) == 1
    ok(api.c.post(f"/api/v1/competitions/{cid}/fixtures/regenerate"))
    assert api.stats(cid)["scorers"] == []


def test_deleting_the_competition_with_stats(api, match):
    cid, fid, p = match["cid"], match["fid"], match["p"]
    ok(api.result(cid, fid, 1, 0, events=[goal(p["Ade"], assist=p["Bola"])]), 201)
    assert api.c.delete(f"/api/v1/competitions/{cid}").status_code == 204


def test_stats_are_only_for_goal_sports(api):
    cid = api.create("league", 2, sport="basketball")
    a, b = api.add_team(cid, "A"), api.add_team(cid, "B")
    pid = ok(api.add_player(cid, a["id"], "Shooter"), 201)["id"]  # squads still work
    f = api.generate(cid)[0]
    r = api.result(cid, f["id"], 80, 70, events=[goal(pid)])
    assert r.status_code == 400 and "aren't kept for this sport" in r.json()["detail"]
    ok(api.result(cid, f["id"], 80, 70), 201)
    assert api.stats(cid)["supported"] is False


def test_knockout_and_two_legged_ties_take_events(api):
    cid = api.create("knockout", 2, teams=2)
    f = api.generate(cid)[0]
    pid = ok(api.add_player(cid, f["home_team_id"], "Hero"), 201)["id"]
    ok(api.result(cid, f["id"], 1, 1, tiebreak="home", events=[goal(pid, minute=90)]), 201)
    assert api.stats(cid)["scorers"][0]["value"] == 1


# ---------------------------------------------------------------------------
# Leaderboards
# ---------------------------------------------------------------------------

def test_leaderboards_rank_and_share_ties(api):
    cid = api.create("league", 3)
    teams = {n: api.add_team(cid, n)["id"] for n in ("A", "B", "C")}
    ps = {}
    for team, names in (("A", ["Ann", "Abe"]), ("B", ["Ben"]), ("C", ["Cat"])):
        for n in names:
            ps[n] = ok(api.add_player(cid, teams[team], n), 201)["id"]
    team_of = {pid: teams[n[0]] for n, pid in ps.items()}
    api.generate(cid)

    plan = {  # (home team, away team) -> events, score fits
        ("A", "B"): [goal(ps["Ann"], assist=ps["Abe"]), goal(ps["Ann"]), goal(ps["Ben"]),
                     {"type": "yellow_card", "player_id": ps["Ben"]}],
        ("A", "C"): [goal(ps["Abe"], assist=ps["Ann"]), {"type": "red_card", "player_id": ps["Cat"]}],
        ("B", "C"): [goal(ps["Ben"]), goal(ps["Cat"]), {"type": "yellow_card", "player_id": ps["Ben"]}],
    }
    name_of = {v: k for k, v in teams.items()}
    for f in api.fixtures(cid):
        h, a = name_of[f["home_team_id"]], name_of[f["away_team_id"]]
        events = plan.get((h, a)) or plan.get((a, h))
        score = {f["home_team_id"]: 0, f["away_team_id"]: 0}
        for e in events:
            if e["type"] == "goal":
                score[team_of[e["player_id"]]] += 1
        ok(api.result(cid, f["id"], score[f["home_team_id"]], score[f["away_team_id"]], events=events), 201)

    stats = api.stats(cid)
    assert stats["supported"] is True
    scorers = [(s["rank"], s["player_name"], s["value"]) for s in stats["scorers"]]
    # Ann 2; Ben 2 (Ann first: more assists); Abe and Cat 1 each, Abe has an assist
    assert scorers == [(1, "Ann", 2), (1, "Ben", 2), (3, "Abe", 1), (3, "Cat", 1)]
    assert stats["scorers"][0]["team_name"] == "A"
    # Level on assists: more goals first
    assert [(s["rank"], s["player_name"]) for s in stats["assists"]] == [(1, "Ann"), (1, "Abe")]
    discipline = [(s["player_name"], s["yellow_cards"], s["red_cards"]) for s in stats["discipline"]]
    assert discipline == [("Cat", 0, 1), ("Ben", 2, 0)]


def test_stats_of_a_public_competition_are_visible_to_others(api, other, match):
    cid = match["cid"]
    assert other.c.get(f"/api/v1/competitions/{cid}/stats/").status_code == 404
    ok(api.patch(cid, is_public=True))
    assert other.stats(cid)["supported"] is True
    assert other.c.get(f"/api/v1/competitions/{cid}/fixtures/{match['fid']}/events").status_code == 200
