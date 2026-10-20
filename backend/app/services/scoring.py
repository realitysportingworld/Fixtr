"""
Sport-specific scoring defaults.

Each config is stored on Competition.scoring_config and used by
the standings calculator. Fields:

    win / draw / loss   — points awarded per match outcome
    score_label         — display label for the score column (Goals, Points, etc.)
    lower_wins          — optional; if true the lower score wins (e.g. golf strokes)
"""
import json
from typing import Optional

MAX_SCORING_CONFIG_BYTES = 2_000

SPORT_DEFAULTS: dict[str, dict] = {
    "football": {
        "win": 3,
        "draw": 1,
        "loss": 0,
        "score_label": "Goals",
    },
    "basketball": {
        "win": 2,
        "draw": 0,
        "loss": 0,
        "score_label": "Points",
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


def get_default_scoring(sport: str) -> dict:
    """Return the default scoring config for a sport."""
    return dict(SPORT_DEFAULTS.get(sport, SPORT_DEFAULTS["custom"]))


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
    if "lower_wins" in config and not isinstance(config["lower_wins"], bool):
        raise ValueError("scoring_config.lower_wins must be true or false")
    if "score_label" in config and not isinstance(config["score_label"], str):
        raise ValueError("scoring_config.score_label must be a string")
    return config


def lower_score_wins(competition) -> bool:
    """Golf-style scoring. Falls back to the sport for configs saved before lower_wins existed."""
    config = competition.scoring_config or {}
    sport = getattr(competition.sport, "value", competition.sport)
    return bool(config.get("lower_wins", sport == "golf"))


def winning_side(home_score: int, away_score: int, lower_wins: bool) -> Optional[str]:
    """Return "home", "away", or None for a draw."""
    if home_score == away_score:
        return None
    home_ahead = home_score < away_score if lower_wins else home_score > away_score
    return "home" if home_ahead else "away"
