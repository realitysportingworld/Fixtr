"""
Sport-specific scoring defaults.

Each config is stored on Competition.scoring_config and used by
the standings calculator. Fields:

    win / draw / loss   — points awarded per match outcome
    score_label         — display label for the score column (Goals, Points, etc.)
    lower_wins          — optional; if true the lower score wins (e.g. golf strokes)
    ranking             — optional; "points" (default) or "win_pct" (NBA-style table)
    allow_draws         — optional, default true; false rejects level league-table results
    preset              — optional; key of the preset the config came from (e.g. "nba")
"""
import json
from typing import Optional

MAX_SCORING_CONFIG_BYTES = 2_000
RANKING_MODES = ("points", "win_pct")

SPORT_DEFAULTS: dict[str, dict] = {
    "football": {
        "win": 3,
        "draw": 1,
        "loss": 0,
        "score_label": "Goals",
    },
    "basketball": {
        # FIBA: 2 points for a win, 1 for a loss; games can't end level
        "win": 2,
        "draw": 0,
        "loss": 1,
        "score_label": "Points",
        "allow_draws": False,
        "preset": "fiba",
    },
    "rugby": {
        "win": 4,
        "draw": 2,
        "loss": 0,
        "score_label": "Points",
    },
    "golf": {
        "win": 2,
        "draw": 1,
        "loss": 0,
        "score_label": "Strokes",
        "lower_wins": True,
    },
    "volleyball": {
        "win": 3,
        "draw": 0,
        "loss": 0,
        "score_label": "Sets",
    },
    "custom": {
        "win": 3,
        "draw": 1,
        "loss": 0,
        "score_label": "Score",
    },
}

# Named rule sets a user can pick per sport; the first is the sport's default.
# Sports without an entry get a single "Standard" preset from SPORT_DEFAULTS.
SCORING_PRESETS: dict[str, list[dict]] = {
    "basketball": [
        {
            "key": "fiba",
            "label": "FIBA (international)",
            "description": "2 points for a win, 1 for a loss. Table ranked by points.",
            "config": SPORT_DEFAULTS["basketball"],
        },
        {
            "key": "nba",
            "label": "NBA",
            "description": "No points: table ranked by win percentage, with games behind the leader.",
            "config": {
                "win": 1,
                "draw": 0,
                "loss": 0,
                "score_label": "Points",
                "allow_draws": False,
                "ranking": "win_pct",
                "preset": "nba",
            },
        },
    ],
}


def get_default_scoring(sport: str) -> dict:
    """Return the default scoring config for a sport."""
    return dict(SPORT_DEFAULTS.get(sport, SPORT_DEFAULTS["custom"]))


def get_scoring_presets(sport: str) -> list[dict]:
    if sport in SCORING_PRESETS:
        return SCORING_PRESETS[sport]
    return [{"key": "standard", "label": "Standard", "description": "", "config": get_default_scoring(sport)}]


def validate_scoring_config(config: Optional[dict]) -> Optional[dict]:
    """Raise ValueError if a user-supplied scoring config has invalid values."""
    if config is None:
        return None
    if len(json.dumps(config)) > MAX_SCORING_CONFIG_BYTES:
        raise ValueError("scoring_config is too large")
    for key in ("win", "draw", "loss"):
        value = config.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValueError(f"scoring_config.{key} must be an integer")
    for key in ("lower_wins", "allow_draws"):
        if key in config and not isinstance(config[key], bool):
            raise ValueError(f"scoring_config.{key} must be true or false")
    if "score_label" in config and not isinstance(config["score_label"], str):
        raise ValueError("scoring_config.score_label must be a string")
    if "ranking" in config and config["ranking"] not in RANKING_MODES:
        raise ValueError(f"scoring_config.ranking must be one of: {', '.join(RANKING_MODES)}")
    if "preset" in config and config["preset"] is not None and not isinstance(config["preset"], str):
        raise ValueError("scoring_config.preset must be a string")
    return config


def lower_score_wins(competition) -> bool:
    """Golf-style scoring. Falls back to the sport for configs saved before lower_wins existed."""
    config = competition.scoring_config or {}
    sport = getattr(competition.sport, "value", competition.sport)
    return bool(config.get("lower_wins", sport == "golf"))


def draws_allowed(competition) -> bool:
    return bool((competition.scoring_config or {}).get("allow_draws", True))


def ranking_mode(competition) -> str:
    return (competition.scoring_config or {}).get("ranking", "points")


def winning_side(home_score: int, away_score: int, lower_wins: bool) -> Optional[str]:
    """Return "home", "away", or None for a draw."""
    if home_score == away_score:
        return None
    home_ahead = home_score < away_score if lower_wins else home_score > away_score
    return "home" if home_ahead else "away"
