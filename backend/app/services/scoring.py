"""
Sport-specific scoring defaults.

Each config is stored on Competition.scoring_config and used by
the standings calculator. Fields:

    win / draw / loss   — points awarded per match outcome
    score_label         — display label for the score column (Goals, Points, etc.)
"""

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
