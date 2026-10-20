"""
Fixture generation algorithms.

Supports:
  - round_robin: every team plays every other team once (or twice for home/away)
  - knockout: single elimination bracket
"""
from typing import List, Tuple


def generate_round_robin(team_ids: List[str], two_legs: bool = False) -> List[List[Tuple[str, str]]]:
    """
    Generate a round-robin fixture schedule using the circle method.

    Returns a list of rounds, each round being a list of (home_id, away_id) tuples.
    Works for both odd and even numbers of teams (adds a BYE for odd).

    Args:
        team_ids: list of team ID strings
        two_legs: if True, each pair plays home and away

    Returns:
        rounds: list of rounds → each round is a list of match tuples
    """
    teams = list(team_ids)

    if len(teams) % 2 != 0:
        teams.append(None)  # BYE placeholder

    n = len(teams)
    rounds = []

    for round_num in range(n - 1):
        round_fixtures = []
        for i in range(n // 2):
            home = teams[i]
            away = teams[n - 1 - i]
            if home is not None and away is not None:
                round_fixtures.append((home, away))
        rounds.append(round_fixtures)

        # Rotate all except the first element (circle method)
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]

    if two_legs:
        # Add a second leg with home/away swapped
        second_leg = [
            [(away, home) for home, away in round_fixtures]
            for round_fixtures in rounds
        ]
        rounds = rounds + second_leg

    return rounds


def bracket_size(num_teams: int) -> int:
    """Smallest power of 2 that fits num_teams (minimum 2)."""
    size = 2
    while size < num_teams:
        size *= 2
    return size


def num_byes(num_teams: int) -> int:
    return bracket_size(num_teams) - num_teams


def arrange_first_round(
    bye_team_ids: List[str], matches: List[Tuple[str, str]]
) -> List[Tuple[str, str | None]]:
    """
    Order first-round entries so each BYE sits next to a real match where
    possible, meaning bye teams meet a match winner in round 2 rather than
    each other. A BYE entry is (team_id, None).
    """
    byes = [(t, None) for t in bye_team_ids]
    matches = list(matches)
    entries = []
    while byes or matches:
        if byes:
            entries.append(byes.pop(0))
        if matches:
            entries.append(matches.pop(0))
    return entries


def generate_knockout_bracket(team_ids: List[str]) -> List[Tuple[str, str | None]]:
    """
    Generate the first round of a single-elimination knockout bracket.

    If the number of teams is not a power of 2, the top seeds (first in the
    list) receive BYEs so that round 2 has a power-of-2 number of teams.
    Later rounds are created after each round completes (see services/knockout.py).

    Args:
        team_ids: list of team ID strings, sorted by seeding

    Returns:
        first-round entries in bracket order. Each is (home_id, away_id);
        away_id None means home_id has a BYE (auto-advances).
    """
    teams = list(team_ids)
    byes = num_byes(len(teams))
    bye_teams, playing = teams[:byes], teams[byes:]
    matches = [(playing[i], playing[i + 1]) for i in range(0, len(playing), 2)]
    return arrange_first_round(bye_teams, matches)


def get_knockout_round_label(num_teams_remaining: int) -> str:
    labels = {
        2: "Final",
        4: "Semi-Final",
        8: "Quarter-Final",
        16: "Round of 16",
        32: "Round of 32",
        64: "Round of 64",
        128: "Round of 128",
    }
    return labels.get(num_teams_remaining, f"Round of {num_teams_remaining}")
