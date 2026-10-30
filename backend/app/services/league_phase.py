"""
LEAGUE_PHASE format (the Champions League model since 2024/25).

All teams sit in one table but each plays only `matches_per_team` different
opponents. When the league phase is finished:
  - the top `direct_qualifiers` go straight into the knockout bracket,
  - the next `playoff_qualifiers` meet in a knockout play-off (9th v 24th,
    10th v 23rd, ... in the UCL), whose winners join them,
  - everyone else is eliminated.
The play-off is stored as the bracket's first round, with the direct
qualifiers on BYEs placed so they meet the right play-off winners.
"""
import random
from collections import Counter, defaultdict
from typing import List, Optional, Tuple

from app.services.fixture_generator import generate_round_robin

MAX_MATCHES_PER_TEAM = 50
PLAYOFF_ROUND_LABEL = "Knockout Play-off"


def _is_power_of_two(n: int) -> bool:
    return n >= 1 and n & (n - 1) == 0


def default_settings(num_teams: int) -> dict:
    """UCL proportions scaled to the competition size (36 teams -> 8 matches, 8 direct, 16 play-off)."""
    bracket = 16 if num_teams >= 24 else 8 if num_teams >= 12 else 4 if num_teams >= 6 else 2
    direct, playoff = bracket // 2, bracket
    if direct + playoff > num_teams:  # only 2 teams
        direct, playoff = 2, 0
    matches = min(8, num_teams - 1)
    if num_teams % 2 and matches % 2:
        matches -= 1
    return {"matches_per_team": matches, "direct_qualifiers": direct, "playoff_qualifiers": playoff}


def settings_error(num_teams: int, matches: int, direct: int, playoff: int, check_parity: bool = True) -> Optional[str]:
    """Why these settings can't work for num_teams, or None if they can."""
    if playoff % 2:
        return "Play-off places must be an even number"
    knockout_size = direct + playoff // 2
    if knockout_size < 2 or not _is_power_of_two(knockout_size):
        return ("Direct qualifiers plus half the play-off places must make a knockout of "
                "2, 4, 8, 16 or 32 teams (e.g. 8 direct + 16 play-off = 16)")
    if direct + playoff > num_teams:
        return f"{direct + playoff} qualifying places but only {num_teams} teams"
    if not 1 <= matches <= min(num_teams - 1, MAX_MATCHES_PER_TEAM):
        return f"Matches per team must be between 1 and {min(num_teams - 1, MAX_MATCHES_PER_TEAM)}"
    if check_parity and (num_teams * matches) % 2:
        return "With an odd number of teams, matches per team must be even"
    return None


def _euler_orient(edges: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """
    Orient each match (home, away) so every team's home and away counts differ
    by at most one. Odd-degree teams are joined to a dummy node so all degrees
    are even; Hierholzer's walk then splits the edges into closed trails, which
    enter and leave every node equally often.
    """
    dummy = object()
    degree = Counter(t for e in edges for t in e)
    all_edges = list(edges) + [(t, dummy) for t, d in degree.items() if d % 2]
    adjacency: dict = defaultdict(list)
    for i, (a, b) in enumerate(all_edges):
        adjacency[a].append((i, b))
        adjacency[b].append((i, a))

    used = [False] * len(all_edges)
    oriented: dict[int, Tuple] = {}
    for start in list(adjacency):
        stack = [start]
        while stack:
            node = stack[-1]
            while adjacency[node] and used[adjacency[node][-1][0]]:
                adjacency[node].pop()
            if adjacency[node]:
                i, other = adjacency[node].pop()
                used[i] = True
                oriented[i] = (node, other)
                stack.append(other)
            else:
                stack.pop()
    return [oriented[i] for i in range(len(edges))]


def _balance_home_away(rounds: List[List[Tuple[str, str]]]) -> List[List[Tuple[str, str]]]:
    oriented = iter(_euler_orient([match for matches in rounds for match in matches]))
    return [[next(oriented) for _ in matches] for matches in rounds]


def _schedule_matchdays(edges: List[Tuple[str, str]]) -> List[List[Tuple[str, str]]]:
    """Greedily split matches into matchdays where nobody plays twice."""
    remaining = list(edges)
    rounds = []
    while remaining:
        load = Counter(t for e in remaining for t in e)
        used, today, later = set(), [], []
        for e in sorted(remaining, key=lambda e: -(load[e[0]] + load[e[1]])):
            if e[0] in used or e[1] in used:
                later.append(e)
            else:
                today.append(e)
                used.update(e)
        rounds.append(today)
        remaining = later
    return rounds


def draw_league_phase(team_ids: List[str], matches_per_team: int, rng: random.Random = random) -> List[List[Tuple[str, str]]]:
    """
    Random draw where every team plays exactly `matches_per_team` different
    opponents, roughly half at home. Returns matchdays of (home, away) pairs.
    """
    teams = list(team_ids)
    rng.shuffle(teams)
    n = len(teams)
    if n % 2 == 0:
        # The first m rounds of a round robin: m distinct opponents, one per matchday
        return _balance_home_away(generate_round_robin(teams)[:matches_per_team])
    # Odd count (m is even): team i plays i±1 .. i±m/2 around a circle. Byes
    # are unavoidable, so this can take a few more matchdays than m.
    edges = [(teams[i], teams[(i + k) % n]) for k in range(1, matches_per_team // 2 + 1) for i in range(n)]
    return _balance_home_away(_schedule_matchdays(edges))


def seed_order(size: int) -> List[int]:
    """Bracket slot order so seeds 1 and 2 can only meet in the final: 4 -> [1, 4, 2, 3]."""
    order = [1]
    while len(order) < size:
        total = len(order) * 2 + 1
        order = [x for s in order for x in (s, total - s)]
    return order


def knockout_entries(ranked_team_ids: List[str], direct: int, playoff: int) -> List[Tuple[str, Optional[str]]]:
    """
    First knockout round entries, in bracket order, from the final table.
    (home, away) has the higher seed first; (team, None) is a direct
    qualifier's BYE through the play-off round.
    """
    by_seed: dict[int, Tuple[str, Optional[str]]] = {}
    if playoff == 0:
        order = seed_order(direct)
        return [(ranked_team_ids[a - 1], ranked_team_ids[b - 1]) for a, b in zip(order[::2], order[1::2])]
    for seed in range(1, direct + 1):
        by_seed[seed] = (ranked_team_ids[seed - 1], None)
    for j in range(playoff // 2):
        # 9th v 24th, 10th v 23rd, ...; the winner takes seed direct+1+j
        by_seed[direct + 1 + j] = (ranked_team_ids[direct + j], ranked_team_ids[direct + playoff - 1 - j])
    return [by_seed[s] for s in seed_order(direct + playoff // 2)]
