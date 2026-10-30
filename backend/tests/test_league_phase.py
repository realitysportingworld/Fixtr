import random
from collections import Counter

import pytest

from app.services import league_phase
from tests.helpers import API, ok


def _draw_cases():
    """Every team count 2-40 with every valid matches-per-team up to 10."""
    for teams in range(2, 41):
        for matches in range(1, min(teams - 1, 10) + 1):
            if teams % 2 == 0 or matches % 2 == 0:
                yield teams, matches


@pytest.mark.parametrize("teams,matches", list(_draw_cases()))
def test_draw_gives_everyone_distinct_opponents_and_balanced_venues(teams, matches):
    ids = [f"t{i}" for i in range(teams)]
    rounds = league_phase.draw_league_phase(ids, matches, random.Random(teams * 100 + matches))
    games = [g for r in rounds for g in r]
    played = Counter(t for g in games for t in g)
    assert set(played.values()) == {matches}
    assert len({frozenset(g) for g in games}) == len(games)                # no rematches
    for r in rounds:                                                        # one match a matchday
        in_round = [t for g in r for t in g]
        assert len(in_round) == len(set(in_round))
    home = Counter(h for h, _ in games)
    assert all(abs(2 * home[t] - matches) <= 1 for t in ids)              # home/away within one


def test_36_teams_8_matches_fits_8_matchdays():
    rounds = league_phase.draw_league_phase([str(i) for i in range(36)], 8, random.Random(1))
    assert len(rounds) == 8


def test_settings_validation(api):
    base = {"name": "bad", "format": "league_phase", "sport": "football", "max_participants": 12}
    r = api.c.post(f"{API}/", json={**base, "format_config": {"direct_qualifiers": 3, "playoff_qualifiers": 4}})
    assert r.status_code == 422 and "knockout of" in r.text
    r = api.c.post(f"{API}/", json={**base, "format_config": {"direct_qualifiers": 8, "playoff_qualifiers": 16}})
    assert r.status_code == 422 and "only 12 teams" in r.text

    # Odd team count with odd matches each can't be drawn
    cid = api.create("league_phase", 6, teams=5, format_config={
        "matches_per_team": 3, "direct_qualifiers": 1, "playoff_qualifiers": 2})
    r = api.c.post(f"{API}/{cid}/fixtures/generate")
    assert r.status_code == 400 and "odd number" in r.text


@pytest.mark.parametrize("teams,two_legged", [(12, False), (13, True), (24, True)])
def test_full_competition(api, teams, two_legged):
    cid = api.create("league_phase", teams, teams=teams, format_config={"two_legged": two_legged})
    cfg = api.get(cid)["format_config"]
    if teams == 13:
        assert cfg["matches_per_team"] == 8
    direct, playoff = cfg["direct_qualifiers"], cfg["playoff_qualifiers"]

    fx = api.generate(cid)
    games = Counter(t for f in fx for t in (f["home_team_id"], f["away_team_id"]))
    assert set(games.values()) == {cfg["matches_per_team"]}
    assert len({frozenset((f["home_team_id"], f["away_team_id"])) for f in fx}) == len(fx)
    r = api.advance(cid)
    assert r.status_code == 400 and "not yet complete" in r.text

    for f in fx:
        ok(api.result(cid, f["id"], 2, 0), 201)
    table = api.standings(cid)
    assert len(table) == teams

    ko = ok(api.advance(cid), 201)
    assert ko[0]["knockout_round"] == "Knockout Play-off"
    byes = [f for f in ko if f["is_bye"]]
    assert {f["home_team_id"] for f in byes} == {row["team_id"] for row in table[:direct]}
    assert len({f["bracket_position"] for f in ko if not f["is_bye"]}) == playoff // 2
    in_playoff = {t for f in ko if not f["is_bye"] for t in (f["home_team_id"], f["away_team_id"])}
    assert in_playoff == {row["team_id"] for row in table[direct:direct + playoff]}
    if two_legged:
        assert all(f["leg"] in (1, 2) for f in ko if not f["is_bye"])

    r = api.result(cid, fx[0]["id"], 0, 0, method="put")
    assert r.status_code == 400 and "locked" in r.text
    assert api.advance(cid).status_code == 400

    assert api.play_knockout_to_end(cid)["status"] == "completed"
    rounds = [f["knockout_round"] for f in api.fixtures(cid) if f["knockout_round"]]
    assert rounds[-1] == "Final" and rounds.count("Final") == 1
