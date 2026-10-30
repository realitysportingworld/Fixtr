import uuid

from tests.helpers import ok


def by_id(api, cid):
    return {f["id"]: f for f in api.fixtures(cid)}


def test_dates_are_stored_and_returned_in_utc(api):
    cid = api.create("league", 4, teams=4)
    f1, f2, f3 = api.generate(cid)[:3]
    ok(api.schedule(cid, [
        {"fixture_id": f1["id"], "scheduled_at": "2026-11-07T15:00:00+01:00"},  # with an offset
        {"fixture_id": f2["id"], "scheduled_at": "2026-11-07T15:00:00Z"},
        {"fixture_id": f3["id"], "scheduled_at": "2026-11-07T15:00:00"},       # no zone = UTC
    ]))
    fixtures = by_id(api, cid)
    assert fixtures[f1["id"]]["scheduled_at"] == "2026-11-07T14:00:00Z"
    assert fixtures[f2["id"]]["scheduled_at"] == "2026-11-07T15:00:00Z"
    assert fixtures[f3["id"]]["scheduled_at"] == "2026-11-07T15:00:00Z"

    ok(api.schedule(cid, [{"fixture_id": f1["id"], "scheduled_at": None}]))      # clear
    assert by_id(api, cid)[f1["id"]]["scheduled_at"] is None


def test_unknown_fixture_changes_nothing(api):
    cid = api.create("league", 4, teams=4)
    f = api.generate(cid)[0]
    other_cid = api.create("league", 2, teams=2)
    foreign = api.generate(other_cid)[0]
    for missing in (str(uuid.uuid4()), foreign["id"]):
        r = api.schedule(cid, [
            {"fixture_id": f["id"], "scheduled_at": "2026-11-07T15:00:00Z"},
            {"fixture_id": missing, "scheduled_at": "2026-11-07T15:00:00Z"},
        ])
        assert r.status_code == 404
    assert by_id(api, cid)[f["id"]]["scheduled_at"] is None


def test_batch_size_limit(api):
    cid = api.create("league", 2, teams=2)
    f = api.generate(cid)[0]
    item = {"fixture_id": f["id"], "scheduled_at": None}
    assert api.schedule(cid, [item] * 1001).status_code == 422
    ok(api.schedule(cid, []))
