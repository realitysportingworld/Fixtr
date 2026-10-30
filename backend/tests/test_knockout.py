from collections import Counter

import pytest

from tests.helpers import ok


def test_byes_advance_and_winner_changes_flow_into_next_round(api):
    cid = api.create("knockout", 6, teams=6)
    fx = api.generate(cid)
    byes = [f for f in fx if f["is_bye"]]
    assert len(fx) == 4 and len(byes) == 2
    assert {f["knockout_round"] for f in fx} == {"Quarter-Final"}
    assert sorted(f["bracket_position"] for f in fx) == [0, 1, 2, 3]

    assert api.result(cid, byes[0]["id"], 1, 0).status_code == 400
    real = [f for f in fx if not f["is_bye"]]
    r = api.result(cid, real[0]["id"], 1, 1)
    assert r.status_code == 400 and "draw" in r.text

    api.play_all(cid)
    semis = api.fixtures(cid, round_number=2)
    assert len(semis) == 2 and all(f["knockout_round"] == "Semi-Final" for f in semis)
    bye_teams = {b["home_team_id"] for b in byes}
    assert all(len({f["home_team_id"], f["away_team_id"]} & bye_teams) == 1 for f in semis)

    # Changing a quarter-final winner swaps them into the semi, no duplicates
    ok(api.result(cid, real[0]["id"], 0, 3, method="put"))
    semis = api.fixtures(cid, round_number=2)
    assert len(semis) == 2
    in_semis = {t for f in semis for t in (f["home_team_id"], f["away_team_id"])}
    assert real[0]["away_team_id"] in in_semis and real[0]["home_team_id"] not in in_semis

    assert api.play_knockout_to_end(cid)["status"] == "completed"
    final = api.fixtures(cid, round_number=3)
    assert len(final) == 1 and final[0]["knockout_round"] == "Final"
    # ...but not once the winner's next match has been played
    assert api.result(cid, real[0]["id"], 5, 0, method="put").status_code == 400


@pytest.mark.parametrize("max_teams,teams", [(6, 5), (4, 3), (2, 2), (10, 9), (16, 16)])
def test_any_bracket_size_plays_to_completion(api, max_teams, teams):
    cid = api.create("knockout", max_teams, teams=teams)
    api.generate(cid)
    assert api.play_knockout_to_end(cid)["status"] == "completed"


def test_manual_fixtures_not_allowed_in_knockout(api):
    cid = api.create("knockout", 4, teams=4)
    api.generate(cid)
    t = api.teams(cid)
    r = api.c.post(f"/api/v1/competitions/{cid}/fixtures/manual",
                   json={"home_team_id": t[0]["id"], "away_team_id": t[1]["id"], "round_number": 9})
    assert r.status_code == 400


def test_single_match_decided_by_tiebreak(api):
    cid = api.create("knockout", 2, teams=2)
    f = api.generate(cid)[0]
    r = api.result(cid, f["id"], 1, 1)
    assert r.status_code == 400 and "draw" in r.text
    res = ok(api.result(cid, f["id"], 1, 1, tiebreak="away"), 201)
    assert res["winner_id"] == f["away_team_id"]
    assert api.get(cid)["status"] == "completed"


def test_two_legged_ties_on_aggregate_with_single_match_final(api):
    cid = api.create("knockout", 8, teams=8, format_config={"two_legged": True})
    assert api.get(cid)["format_config"] == {"two_legged": True}
    fx = api.generate(cid)
    assert len(fx) == 8 and Counter(f["leg"] for f in fx) == {1: 4, 2: 4}

    def tie(fixtures, position):
        return sorted([f for f in fixtures if f["bracket_position"] == position], key=lambda f: f["leg"])

    leg1, leg2 = tie(fx, 0)
    assert leg1["home_team_id"] == leg2["away_team_id"] and leg1["away_team_id"] == leg2["home_team_id"]
    r = api.result(cid, leg2["id"], 1, 0)
    assert r.status_code == 400 and "first leg" in r.text
    ok(api.result(cid, leg1["id"], 1, 1), 201)                       # first legs can be level
    r = api.result(cid, leg2["id"], 2, 2)
    assert r.status_code == 400 and "aggregate" in r.text
    res = ok(api.result(cid, leg2["id"], 2, 2, tiebreak="away"), 201)  # 3-3, away wins on pens
    assert res["winner_id"] == leg2["away_team_id"]

    # Decided on aggregate even though leg 2's home side won the leg
    first, second = tie(fx, 1)
    ok(api.result(cid, first["id"], 3, 0), 201)
    res = ok(api.result(cid, second["id"], 1, 0), 201)
    assert res["winner_id"] == second["away_team_id"]
    for p in (2, 3):
        first, second = tie(fx, p)
        ok(api.result(cid, first["id"], 0, 1), 201)
        ok(api.result(cid, second["id"], 1, 0, tiebreak="home"), 201)

    semis = api.fixtures(cid, round_number=2)
    assert len(semis) == 4 and {f["leg"] for f in semis} == {1, 2}
    assert semis[0]["knockout_round"] == "Semi-Final"

    # Editing tie 1's first leg flips the aggregate: winner swaps into both semi legs
    old_winner, new_winner = leg2["away_team_id"], leg2["home_team_id"]
    ok(api.result(cid, leg1["id"], 0, 5, method="put"))
    semi = [f for f in api.fixtures(cid, round_number=2) if f["bracket_position"] == 0]
    assert all(new_winner in (f["home_team_id"], f["away_team_id"]) for f in semi)
    assert all(old_winner not in (f["home_team_id"], f["away_team_id"]) for f in semi)

    assert api.play_knockout_to_end(cid)["status"] == "completed"
    final = [f for f in api.fixtures(cid) if f["knockout_round"] == "Final"]
    assert len(final) == 1 and final[0]["leg"] is None and final[0]["winner_id"]
