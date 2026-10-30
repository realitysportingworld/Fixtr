from tests.helpers import ok


def test_league_result_cleared_updates_table_and_reopens(api):
    cid = api.create("league", 4, teams=4)
    api.generate(cid)
    api.play_all(cid)
    assert api.get(cid)["status"] == "completed"
    f = api.fixtures(cid)[0]

    assert api.clear(cid, f["id"]).status_code == 204
    cleared = next(x for x in api.fixtures(cid) if x["id"] == f["id"])
    assert cleared["status"] == "scheduled" and cleared["home_score"] is None and cleared["winner_id"] is None
    assert sum(r["played"] for r in api.standings(cid)) == 10
    assert api.get(cid)["status"] == "active"

    assert api.clear(cid, f["id"]).status_code == 404               # nothing left to clear
    ok(api.result(cid, f["id"], 1, 1), 201)                          # can be entered again with POST
    assert api.get(cid)["status"] == "completed"


def test_stage_results_locked_once_knockout_starts(api):
    cid = api.create("group_knockout", 8, teams=8, num_groups=2)
    api.generate(cid)
    api.play_all(cid)
    group_match = api.fixtures(cid)[0]
    ok(api.advance(cid), 201)
    r = api.clear(cid, group_match["id"])
    assert r.status_code == 400 and "locked" in r.text


def test_knockout_clear_removes_next_tie_and_rebuilds_it(api):
    cid = api.create("knockout", 4, teams=4)
    semi1, semi2 = sorted(api.generate(cid), key=lambda f: f["bracket_position"])
    ok(api.result(cid, semi1["id"], 2, 0), 201)
    ok(api.result(cid, semi2["id"], 2, 0), 201)
    final = api.fixtures(cid, round_number=2)
    assert len(final) == 1

    # Clearing a semi takes the unplayed final away again
    assert api.clear(cid, semi1["id"]).status_code == 204
    assert api.fixtures(cid, round_number=2) == []

    # A different winner this time: the final is rebuilt with them
    ok(api.result(cid, semi1["id"], 0, 2), 201)
    final = api.fixtures(cid, round_number=2)
    assert len(final) == 1
    assert {final[0]["home_team_id"], final[0]["away_team_id"]} == {semi1["away_team_id"], semi2["home_team_id"]}

    # Final played: the competition is over, and the semis can't be cleared
    ok(api.result(cid, final[0]["id"], 1, 0), 201)
    assert api.get(cid)["status"] == "completed"
    r = api.clear(cid, semi1["id"])
    assert r.status_code == 400 and "next-round" in r.text

    # Clearing the final reopens the competition
    assert api.clear(cid, final[0]["id"]).status_code == 204
    assert api.get(cid)["status"] == "active"
    assert api.clear(cid, semi2["id"]).status_code == 204
    assert api.fixtures(cid, round_number=2) == []


def test_other_ties_in_the_next_round_are_kept(api):
    cid = api.create("knockout", 8, teams=8)
    api.generate(cid)
    api.play_all(cid)
    semis = api.fixtures(cid, round_number=2)
    assert len(semis) == 2
    quarter = api.fixtures(cid, round_number=1)[0]
    affected = quarter["bracket_position"] // 2

    assert api.clear(cid, quarter["id"]).status_code == 204
    kept = api.fixtures(cid, round_number=2)
    assert [f["bracket_position"] for f in kept] == [1 - affected]
    assert kept[0]["id"] == next(f["id"] for f in semis if f["bracket_position"] != affected)

    ok(api.result(cid, quarter["id"], 2, 1), 201)
    assert sorted(f["bracket_position"] for f in api.fixtures(cid, round_number=2)) == [0, 1]


def test_two_legged_ties_clear_second_leg_first(api):
    cid = api.create("knockout", 4, teams=4, format_config={"two_legged": True})
    fx = api.generate(cid)
    leg1, leg2 = sorted([f for f in fx if f["bracket_position"] == 0], key=lambda f: f["leg"])
    ok(api.result(cid, leg1["id"], 1, 0), 201)
    ok(api.result(cid, leg2["id"], 1, 0, tiebreak="home"), 201)

    r = api.clear(cid, leg1["id"])
    assert r.status_code == 400 and "second leg" in r.text
    assert api.clear(cid, leg2["id"]).status_code == 204
    assert api.clear(cid, leg1["id"]).status_code == 204


def test_bye_and_cancelled(api):
    cid = api.create("knockout", 3, teams=3)
    fx = api.generate(cid)
    bye = next(f for f in fx if f["is_bye"])
    assert api.clear(cid, bye["id"]).status_code == 400

    cid = api.create("league", 2, teams=2)
    f = api.generate(cid)[0]
    ok(api.result(cid, f["id"], 1, 0), 201)
    ok(api.patch(cid, status="cancelled"))
    assert api.clear(cid, f["id"]).status_code == 400
