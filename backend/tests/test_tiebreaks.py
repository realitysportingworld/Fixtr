import pytest

from tests.helpers import ok

# A and B finish on 6 points each. B has the better goal difference (+5 v +1),
# but A beat B. C and D are clear of them.
RESULTS = [
    ("A", "B", 1, 0),
    ("A", "C", 0, 1),
    ("A", "D", 1, 0),
    ("B", "C", 5, 0),
    ("B", "D", 1, 0),
    ("C", "D", 0, 0),
]


def play(api, cid, results=RESULTS):
    names = {t["id"]: t["name"] for t in api.teams(cid)}
    for f in api.fixtures(cid):
        home, away = names[f["home_team_id"]], names[f["away_team_id"]]
        for a, b, sa, sb in results:
            if (home, away) == (a, b):
                ok(api.result(cid, f["id"], sa, sb), 201)
            elif (home, away) == (b, a):
                ok(api.result(cid, f["id"], sb, sa), 201)


def league(api, teams="ABCD", results=RESULTS, **scoring):
    cid = api.create("league", len(teams), scoring_config=scoring or None)
    for name in teams:
        api.add_team(cid, name)
    api.generate(cid)
    play(api, cid, results)
    return cid


def order(api, cid):
    return [r["team_name"] for r in api.standings(cid)]


def test_default_is_goal_difference_first(api):
    cid = league(api)
    table = api.standings(cid)
    assert [r["points"] for r in table[:2]] == [6, 6]
    assert order(api, cid) == ["B", "A", "C", "D"]


def test_head_to_head_first(api):
    cid = league(api, tiebreak="head_to_head")
    assert order(api, cid) == ["A", "B", "C", "D"]
    # Switching the rule re-ranks straight away
    ok(api.patch(cid, scoring_config={"tiebreak": "score_difference"}))
    assert order(api, cid) == ["B", "A", "C", "D"]


def test_head_to_head_with_win_percentage(api):
    cid = league(api, ranking="win_pct", tiebreak="head_to_head")
    assert order(api, cid) == ["A", "B", "C", "D"]


def test_head_to_head_settles_teams_level_on_everything_else(api):
    # Zebras and Ants: 4 points, goal difference 0, 1 scored each. Zebras won
    # their meeting, so they go above Ants instead of falling back to the alphabet.
    results = [
        ("Zebras", "Ants", 1, 0),
        ("Zebras", "C", 0, 0),
        ("Zebras", "D", 0, 1),
        ("Ants", "C", 1, 0),
        ("Ants", "D", 0, 0),
        ("C", "D", 2, 2),
    ]
    cid = league(api, teams=["Zebras", "Ants", "C", "D"], results=results)
    table = {r["team_name"]: r for r in api.standings(cid)}
    level = lambda r: (r["points"], r["goal_difference"], r["goals_for"])  # noqa: E731
    assert level(table["Zebras"]) == level(table["Ants"]) == (4, 0, 1)
    names = order(api, cid)
    assert names.index("Zebras") < names.index("Ants")
