"""
Fixture generation algorithms.

Supports:
  - round_robin: every team plays every other team once (or twice for home/away)
  - knockout: single elimination bracket
"""
from typing import List, Tuple
import uuid


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


def generate_knockout_bracket(team_ids: List[str]) -> List[List[Tuple[str | None, str | None]]]:
    """
    Generate a single-elimination knockout bracket.

    The number of teams must be a power of 2. If not, byes are added to
    pad up to the next power of 2.

    Returns rounds in order: [Round of 16, QF, SF, Final]
    Each match is (home_id, away_id) — None means a BYE (auto-advance).

    Args:
        team_ids: list of team ID strings (ideally sorted by seeding)

    Returns:
        rounds: list of rounds, each a list of match tuples
    """
    import math

    n = len(team_ids)
    # Pad to next power of 2
    next_power = 2 ** math.ceil(math.log2(n)) if n > 1 else 1
    teams = list(team_ids) + [None] * (next_power - n)

    rounds = []
    current_round = [(teams[i], teams[i + 1]) for i in range(0, len(teams), 2)]
    rounds.append(current_round)

    # Remaining rounds are TBD placeholders (winners determined after each result)
    num_remaining = int(math.log2(next_power)) - 1
    for _ in range(num_remaining):
        prev = rounds[-1]
        tbd_round = [(None, None)] * (len(prev) // 2)
        rounds.append(tbd_round)

    return rounds


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
