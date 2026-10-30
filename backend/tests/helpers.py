"""Small client wrapper so tests read as competition steps, not HTTP plumbing."""
import itertools

from fastapi.testclient import TestClient

API = "/api/v1/competitions"
_names = itertools.count()


def ok(response, code: int = 200):
    assert response.status_code == code, (response.status_code, response.text)
    return response.json() if response.content else None


class Api:
    def __init__(self, client: TestClient):
        self.c = client

    # Competitions
    def create(self, fmt: str, max_teams: int, teams: int = 0, sport: str = "football", **extra) -> str:
        body = {"name": f"{fmt} {next(_names)}", "format": fmt, "sport": sport,
                "max_participants": max_teams, **extra}
        cid = ok(self.c.post(f"{API}/", json=body), 201)["id"]
        for i in range(teams):
            self.add_team(cid, f"T{i}")
        return cid

    def get(self, cid: str) -> dict:
        return ok(self.c.get(f"{API}/{cid}"))

    def patch(self, cid: str, **fields):
        return self.c.patch(f"{API}/{cid}", json=fields)

    def add_team(self, cid: str, name: str) -> dict:
        return ok(self.c.post(f"{API}/{cid}/teams/", json={"name": name}), 201)

    def teams(self, cid: str) -> list[dict]:
        return ok(self.c.get(f"{API}/{cid}/teams/"))

    # Fixtures
    def generate(self, cid: str) -> list[dict]:
        return ok(self.c.post(f"{API}/{cid}/fixtures/generate"), 201)

    def fixtures(self, cid: str, **params) -> list[dict]:
        return ok(self.c.get(f"{API}/{cid}/fixtures/", params=params))

    def advance(self, cid: str, teams_per_group: int = 2):
        return self.c.post(f"{API}/{cid}/fixtures/advance-to-knockout", json={"teams_per_group": teams_per_group})

    def schedule(self, cid: str, items: list[dict]):
        return self.c.patch(f"{API}/{cid}/fixtures/schedule", json=items)

    # Results
    def result(self, cid: str, fid: str, home: int, away: int, tiebreak: str | None = None, method: str = "post"):
        body = {"home_score": home, "away_score": away}
        if tiebreak:
            body["tiebreak_winner"] = tiebreak
        return getattr(self.c, method)(f"{API}/{cid}/fixtures/{fid}/result", json=body)

    def clear(self, cid: str, fid: str):
        return self.c.delete(f"{API}/{cid}/fixtures/{fid}/result")

    def play_all(self, cid: str, home: int = 2, away: int = 1) -> int:
        """Play every scheduled fixture with the same score. Returns how many were played."""
        played = 0
        for f in self.fixtures(cid):
            if f["status"] == "scheduled":
                ok(self.result(cid, f["id"], home, away), 201)
                played += 1
        return played

    def play_knockout_to_end(self, cid: str) -> dict:
        """Play open knockout fixtures 3-1 (level ties to home) until none are left."""
        for _ in range(40):
            open_ = [f for f in self.fixtures(cid) if f["knockout_round"] and f["status"] == "scheduled"]
            if not open_:
                break
            for f in sorted(open_, key=lambda f: f["leg"] or 0):
                ok(self.result(cid, f["id"], 3, 1, tiebreak="home"), 201)
        return self.get(cid)

    # Tables
    def standings(self, cid: str) -> list[dict]:
        return ok(self.c.get(f"{API}/{cid}/standings/"))

    def groups(self, cid: str) -> list[dict]:
        return ok(self.c.get(f"{API}/{cid}/groups/"))
