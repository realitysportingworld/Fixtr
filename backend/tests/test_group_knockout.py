from tests.helpers import API, ok


def test_groups_then_knockout(api):
    cid = api.create("group_knockout", 12, teams=12, num_groups=3)
    api.generate(cid)
    groups = api.groups(cid)
    assert len(groups) == 3

    a, b = groups[0]["standings"][0]["team_id"], groups[1]["standings"][0]["team_id"]
    r = api.c.post(f"{API}/{cid}/fixtures/manual", json={"home_team_id": a, "away_team_id": b, "round_number": 9})
    assert r.status_code == 400                                   # across groups
    a2 = groups[0]["standings"][1]["team_id"]
    ok(api.c.post(f"{API}/{cid}/fixtures/manual",
                  json={"home_team_id": a, "away_team_id": a2, "round_number": 9}), 201)
    assert api.advance(cid, teams_per_group=0).status_code == 422

    api.play_all(cid)
    groups = api.groups(cid)
    assert sum(s["played"] for s in groups[0]["standings"]) == 14  # 6 matches + manual, x2

    ko = ok(api.advance(cid), 201)
    assert len(ko) == 4 and sum(f["is_bye"] for f in ko) == 2
    team_group = {s["team_id"]: g["id"] for g in groups for s in g["standings"]}
    assert all(team_group[f["home_team_id"]] != team_group[f["away_team_id"]] for f in ko if not f["is_bye"])

    before = api.groups(cid)
    assert api.play_knockout_to_end(cid)["status"] == "completed"
    assert api.groups(cid) == before                              # knockout doesn't touch group tables


def test_regenerate_after_knockout_then_delete(api):
    cid = api.create("group_knockout", 8, teams=8, num_groups=2)
    api.generate(cid)
    api.play_all(cid)
    ok(api.advance(cid), 201)
    api.play_all(cid)
    ok(api.c.post(f"{API}/{cid}/fixtures/regenerate"))
    assert len(api.groups(cid)) == 2
    assert all(f["status"] == "scheduled" for f in api.fixtures(cid))
    api.play_all(cid)
    assert api.c.delete(f"{API}/{cid}").status_code == 204


def test_setup_validation(api):
    def create(**kw):
        return api.c.post(f"{API}/", json={"name": "g", "format": "group_knockout", "sport": "football", **kw})

    assert create(max_participants=8).status_code == 422                # num_groups missing
    assert create(max_participants=8, num_groups=1).status_code == 422
    assert create(max_participants=5, num_groups=3).status_code == 422  # < 2 per group
    r = api.c.post(f"{API}/", json={"name": "l", "format": "league", "sport": "football",
                                    "max_participants": 4, "num_groups": 3})
    assert ok(r, 201)["num_groups"] is None

    cid = api.create("group_knockout", 8, teams=5, num_groups=3)        # only 5 of 6 needed
    r = api.c.post(f"{API}/{cid}/fixtures/generate")
    assert r.status_code == 400 and "Need at least 6" in r.text
    assert api.get(cid)["status"] == "draft" and api.groups(cid) == []


def test_group_results_lock_once_knockout_starts(api):
    cid = api.create("group_knockout", 8, teams=8, num_groups=2)
    api.generate(cid)
    api.play_all(cid)
    gf = api.fixtures(cid)[0]
    ok(api.result(cid, gf["id"], 0, 0, method="put"))             # still editable
    ok(api.advance(cid), 201)
    r = api.result(cid, gf["id"], 4, 0, method="put")
    assert r.status_code == 400 and "locked" in r.text
    r = api.c.post(f"{API}/{cid}/fixtures/manual", json={
        "home_team_id": gf["home_team_id"], "away_team_id": gf["away_team_id"], "round_number": 9})
    assert r.status_code == 400
