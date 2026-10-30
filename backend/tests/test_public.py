from tests.helpers import API, ok


def test_search_and_read_only_viewing(api, other):
    cid = ok(api.c.post(f"{API}/", json={"name": "Sunday 100% League", "format": "group_knockout",
                                         "sport": "football", "max_participants": 8, "num_groups": 2}), 201)["id"]
    for i in range(8):
        api.add_team(cid, f"P{i}")
    fx = api.generate(cid)
    ok(api.result(cid, fx[0]["id"], 2, 0), 201)

    # Private by default
    assert other.c.get(f"{API}/{cid}").status_code == 404
    assert ok(other.c.get(f"{API}/public", params={"q": "Sunday"})) == []

    ok(api.patch(cid, is_public=True))
    found = ok(other.c.get(f"{API}/public", params={"q": "100%"}))
    assert [x["id"] for x in found] == [cid] and found[0]["owner_username"] == "admin"
    assert ok(other.c.get(f"{API}/public", params={"q": "admin"}))[0]["id"] == cid   # by organiser
    assert ok(other.c.get(f"{API}/public", params={"q": "%"}))[0]["id"] == cid       # literal %
    assert ok(other.c.get(f"{API}/public", params={"q": "_"})) == []                 # literal _
    assert other.c.get(f"{API}/public", params={"q": "x" * 101}).status_code == 422
    for path in ("", "/teams/", "/fixtures/", "/standings/", "/groups/"):
        ok(other.c.get(f"{API}/{cid}{path}"))

    # ...but can't change anything
    assert other.patch(cid, name="mine").status_code == 404
    assert other.result(cid, fx[2]["id"], 1, 0).status_code == 404
    assert other.clear(cid, fx[0]["id"]).status_code == 404
    assert other.schedule(cid, [{"fixture_id": fx[1]["id"], "scheduled_at": None}]).status_code == 404
    assert other.c.delete(f"{API}/{cid}").status_code == 404
    assert other.c.post(f"{API}/{cid}/fixtures/regenerate").status_code == 404
    assert cid not in [x["id"] for x in ok(other.c.get(f"{API}/"))]  # "my competitions" stays mine
    ok(api.result(cid, fx[1]["id"], 1, 0), 201)                       # owner still can

    ok(api.patch(cid, is_public=False))
    assert other.c.get(f"{API}/{cid}/fixtures/").status_code == 404
