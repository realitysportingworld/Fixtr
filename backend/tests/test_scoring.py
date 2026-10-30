from tests.helpers import API, ok


def test_golf_lower_score_wins(api):
    cid = api.create("league", 2, teams=2, sport="golf")
    f = api.generate(cid)[0]
    res = ok(api.result(cid, f["id"], 70, 74), 201)
    assert res["winner_id"] == f["home_team_id"]
    table = api.standings(cid)
    assert table[0]["team_id"] == f["home_team_id"] and table[0]["wins"] == 1


def test_scoring_config_validation(api):
    base = {"name": "x", "format": "league", "sport": "custom", "max_participants": 4}
    assert api.c.post(f"{API}/", json={**base, "scoring_config": {"win": "three"}}).status_code == 422
    assert api.c.post(f"{API}/", json={**base, "scoring_config": {"ranking": "elo"}}).status_code == 422
    assert api.c.post(f"{API}/", json={**base, "scoring_config": {"tiebreak": "coin_toss"}}).status_code == 422
    ok(api.c.post(f"{API}/", json={**base, "scoring_config": {"win": 2, "draw": 1, "loss": 0, "lower_wins": False}}),
       201)


def test_config_merges_over_defaults_and_recalculates(api):
    cid = api.create("league", 2, teams=2, scoring_config={"win": 5})
    assert api.get(cid)["scoring_config"] == {"win": 5, "draw": 1, "loss": 0, "score_label": "Goals"}
    f = api.generate(cid)[0]
    ok(api.result(cid, f["id"], 3, 1), 201)
    assert api.standings(cid)[0]["points"] == 5

    cfg = ok(api.patch(cid, scoring_config={"win": 2}))["scoring_config"]
    assert cfg["win"] == 2 and cfg["score_label"] == "Goals"
    assert api.standings(cid)[0]["points"] == 2

    # Flipping lower_wins re-decides league results
    ok(api.patch(cid, scoring_config={"lower_wins": True}))
    table = api.standings(cid)
    assert table[0]["team_id"] == f["away_team_id"] and table[0]["wins"] == 1


def test_lower_wins_locked_once_knockout_has_results(api):
    cid = api.create("knockout", 2, teams=2)
    f = api.generate(cid)[0]
    ok(api.result(cid, f["id"], 3, 1), 201)
    assert api.patch(cid, scoring_config={"lower_wins": True}).status_code == 400
    assert api.get(cid)["scoring_config"].get("lower_wins") is None


def test_basketball_presets(api):
    presets = ok(api.c.get(f"{API}/scoring-presets"))
    assert [p["key"] for p in presets["basketball"]] == ["fiba", "nba"]
    assert presets["football"][0]["key"] == "standard"

    cid = api.create("league", 4, teams=4, sport="basketball")
    cfg = api.get(cid)["scoring_config"]
    assert cfg["loss"] == 1 and cfg["allow_draws"] is False and cfg["preset"] == "fiba"
    assert cfg["tiebreak"] == "head_to_head"
    fx = api.generate(cid)
    r = api.result(cid, fx[0]["id"], 80, 80)
    assert r.status_code == 400 and "Draws aren't allowed" in r.text
    for f in fx:
        ok(api.result(cid, f["id"], 90, 80), 201)
    table = api.standings(cid)
    assert all(row["points"] == 2 * row["wins"] + row["losses"] for row in table)  # FIBA 2/1

    nba = next(p for p in presets["basketball"] if p["key"] == "nba")["config"]
    ok(api.patch(cid, scoring_config=nba))
    table = api.standings(cid)
    pcts = [row["win_pct"] for row in table]
    assert pcts == sorted(pcts, reverse=True) and table[0]["games_behind"] == 0
    leader = table[0]
    for row in table:
        assert row["games_behind"] == ((leader["wins"] - row["wins"]) + (row["losses"] - leader["losses"])) / 2
        assert row["win_pct"] == round(row["wins"] / row["played"], 3)


def test_cannot_turn_draws_off_with_drawn_results(api):
    cid = api.create("league", 4, teams=4)
    fx = api.generate(cid)
    ok(api.result(cid, fx[0]["id"], 1, 1), 201)
    r = api.patch(cid, scoring_config={"allow_draws": False})
    assert r.status_code == 400 and "draws" in r.text
