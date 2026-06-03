"""Constants, thresholds, and metric definitions for the regression dashboard."""

from pathlib import Path

# --- Season scope ---
SEASONS = [2023, 2024, 2025]
ANALYSIS_SEASON = 2025
OUTLOOK_SEASON = 2026
ROSTER_SEASON_FOR_OUTLOOK = 2025
CURRENT_SEASON = ANALYSIS_SEASON
BASELINE_SEASONS = [2023, 2024]

# Z-scores: peak-age cohort mean/std (prior season) + age curve in composite.
METRICS_SCORING_VERSION = 13

# Prime-age windows for baseline cohort (inclusive). Peak = reference mean for z-scores.
POSITION_PEAK_AGE: dict[str, dict[str, int]] = {
    "RB": {"peak_min": 24, "peak_max": 25, "productive_min": 23, "productive_max": 26},
    "WR": {"peak_min": 25, "peak_max": 28, "productive_min": 23, "productive_max": 29},
    "QB": {"peak_min": 27, "peak_max": 30, "productive_min": 25, "productive_max": 31},
    "TE": {"peak_min": 26, "peak_max": 29, "productive_min": 24, "productive_max": 30},
}


def z_score_baseline_season(season: int) -> int:
    """Season whose qualified population defines league mean/std for z-scores."""
    return season - 1

# --- Paths ---
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
CACHE_MAX_AGE_DAYS = 7

# --- Regression thresholds ---
REGRESSION_Z_THRESHOLD = 1.28  # legacy single-metric view only

# --- v12 tag cutoffs (role_z / efficiency_z / production_z axes) ---
# "High" / "low" on an axis = at or above / at or below these z values.
TAG_AXIS_HIGH_Z = 1.0
TAG_AXIS_LOW_Z = -0.5
TAG_Z_THRESHOLD = TAG_AXIS_HIGH_Z  # alias used in docs

# star: production + efficiency both strong (no age gate)
TAG_STAR_MIN_PRODUCTION_Z = TAG_AXIS_HIGH_Z
TAG_STAR_MIN_EFFICIENCY_Z = TAG_AXIS_HIGH_Z

# regress_negative: lucky box score, usage without results, or TD luck
TAG_REGRESS_MIN_PRODUCTION_Z = TAG_AXIS_HIGH_Z
TAG_REGRESS_MAX_EFFICIENCY_Z = TAG_AXIS_LOW_Z
TAG_REGRESS_MIN_ROLE_Z = TAG_AXIS_HIGH_Z
TAG_REGRESS_MAX_PRODUCTION_Z = TAG_AXIS_LOW_Z
TAG_TD_LUCK_MAX_EFFICIENCY_Z = 0.0  # td-luck path only if eff_z <= this
TAG_TD_LUCK_MIN_TD_RATE_Z = TAG_AXIS_HIGH_Z

# breakout: efficient but low role; must meet qualify_* volume mins (no age gate)
TAG_BREAKOUT_MAX_ROLE_Z = TAG_AXIS_LOW_Z
TAG_BREAKOUT_MIN_EFFICIENCY_Z = TAG_AXIS_HIGH_Z

# Added to efficiency_z: young (below productive window) boosts, older players penalized.
# Uses signed age_curve_value (negative = young, positive = past productive max).
EFFICIENCY_AGE_Z_PER_YEAR = 0.25

# positive_outlook: low production, strong efficiency
TAG_OUTLOOK_MAX_PRODUCTION_Z = TAG_AXIS_LOW_Z
TAG_OUTLOOK_MIN_EFFICIENCY_Z = TAG_AXIS_HIGH_Z

# v12: three-axis scoring (see Math.txt). Each list is metric IDs averaged into that score.
SCORE_METRICS: dict[str, dict[str, list[str]]] = {
    "QB": {
        "role": ["vol_dropbacks"],
        "efficiency": ["qb_cpoe", "qb_epa_per_play"],
        # Yards + TDs only; INT z was compressing elite volume QBs (~1.0 prod z → ~85th norm pct).
        "production": ["vol_pass_yds", "vol_pass_tds"],
        "td_luck": ["qb_td_rate"],
    },
    "RB": {
        "role": ["opportunity_share"],
        "efficiency": ["rb_ryoe", "rb_efficiency"],
        "production": ["rb_scrimmage_yards", "rb_total_tds"],
        "td_luck": ["rb_td_rate"],
    },
    "WR": {
        "role": ["opportunity_share"],
        "efficiency": ["recv_ypt", "recv_separation", "recv_yac_oe"],
        "production": ["vol_rec_yds", "vol_receptions", "vol_rec_tds"],
        "td_luck": ["recv_td_share"],
    },
    "TE": {
        "role": ["opportunity_share"],
        "efficiency": ["recv_ypt", "recv_separation", "recv_yac_oe"],
        "production": ["vol_rec_yds", "vol_receptions", "vol_rec_tds"],
        "td_luck": ["recv_td_share"],
    },
}

# Optional weights for axis z means (must sum to 1.0 per group). Omitted positions/groups → equal mean.
SCORE_AXIS_WEIGHTS: dict[str, dict[str, dict[str, float]]] = {
    "WR": {
        "efficiency": {
            "recv_ypt": 0.70,
            "recv_separation": 0.15,
            "recv_yac_oe": 0.15,
        },
    },
    "TE": {
        "efficiency": {
            "recv_ypt": 0.70,
            "recv_separation": 0.15,
            "recv_yac_oe": 0.15,
        },
    },
}

# Flags included in OUTLOOK_SEASON view (non-neutral regression signals)
OUTLOOK_REGRESSION_FLAGS = (
    "star",
    "regress_negative",
    "breakout",
    "positive_outlook",
)

# --- Qualification minimums (season-to-date) ---
QUALIFY_MIN_DROPBACKS_QB = 100
QUALIFY_MIN_TARGETS_RECV = 40
QUALIFY_MIN_CARRIES_RB = 60

POSITIONS = ["QB", "WR", "TE", "RB"]
LEADERBOARD_DEFAULT_POSITION = "QB"

# v12 player tags (assign_player_tag in calculator.py).
PLAYER_FLAG_KEYS = (
    "star",
    "regress_negative",
    "breakout",
    "positive_outlook",
    "neutral",
)

FLAG_LABELS = {
    "star": "Star (prod + efficiency)",
    "regress_negative": "Negative regression risk",
    "breakout": "Breakout (low role, high efficiency)",
    "positive_outlook": "Positive outlook (low prod, high efficiency)",
    "neutral": "Neutral",
}

# Shorter labels for chart legends (avoids overlap on scatter)
FLAG_LEGEND_LABELS = {
    "star": "Star",
    "regress_negative": "Neg. risk",
    "breakout": "Breakout",
    "positive_outlook": "Pos. outlook",
    "neutral": "Neutral",
}

FLAG_COLORS = {
    "star": "#1f6feb",
    "regress_negative": "#f85149",
    "breakout": "#3fb950",
    "positive_outlook": "#58a6ff",
    "neutral": "#8b949e",
}

# v11 cache / single-metric regression helper → v12 tag
LEGACY_FLAG_ALIASES = {
    "regress_positive": "positive_outlook",
    "elite_sustainable": "star",
}


def normalize_player_flag(flag: str | None) -> str:
    """Map stored flag values to a v12 PLAYER_FLAG_KEYS tag."""
    if not flag:
        return "neutral"
    flag = str(flag)
    flag = LEGACY_FLAG_ALIASES.get(flag, flag)
    if flag in PLAYER_FLAG_KEYS:
        return flag
    return "neutral"

# Leaderboard "Focus score" dropdown (v12 axes only).
METRIC_VIEW_PRODUCTION = "production_z"
METRIC_VIEW_ROLE = "role_z"
METRIC_VIEW_EFFICIENCY = "efficiency_z"
METRIC_VIEW_COMPOSITE = METRIC_VIEW_PRODUCTION  # backward-compatible alias

LEADERBOARD_SCORE_VIEW_OPTIONS: tuple[tuple[str, str], ...] = (
    (METRIC_VIEW_PRODUCTION, "Production Z"),
    (METRIC_VIEW_ROLE, "Role Z"),
    (METRIC_VIEW_EFFICIENCY, "Efficiency Z"),
)


def normalize_score_view(metric_view: str | None) -> str:
    """Map focus dropdown value to a v12 score column id."""
    if not metric_view or metric_view == "composite":
        return METRIC_VIEW_PRODUCTION
    if metric_view in {METRIC_VIEW_PRODUCTION, METRIC_VIEW_ROLE, METRIC_VIEW_EFFICIENCY}:
        return metric_view
    return METRIC_VIEW_PRODUCTION


def score_view_z_column(metric_view: str | None) -> str:
    """DataFrame column used for sort / percentile for the selected score view."""
    return normalize_score_view(metric_view)


def score_view_label(metric_view: str | None) -> str:
    view = normalize_score_view(metric_view)
    for value, label in LEADERBOARD_SCORE_VIEW_OPTIONS:
        if value == view:
            return label
    return "Production Z"

# --- Composite z-score weights by metric category ---
METRIC_WEIGHTS = {
    "target_share": 1.5,
    "td_rate": 0.75,
    "process": 1.0,  # CPOE, separation, RYOE, etc.
    "pressure": 1.25,
    "yards_per_target": 2.0,
    "rb_efficiency": 1.5,
    "default": 1.0,
    "volume": 1.0,
}

# Age curve composite weight by position (years outside productive window).
AGE_CURVE_WEIGHT_BY_POSITION = {
    "RB": 1.25,
    "WR": 1.0,
    "TE": 1.0,
    "QB": 0.5,
}

# Raw season counting stats (also exposed as vol_* metrics in METRIC_DEFINITIONS)
VOLUME_STAT_FIELDS = [
    "pass_attempts",
    "completions",
    "passing_yards",
    "passing_tds",
    "interceptions",
    "carries",
    "rushing_yards",
    "rushing_tds",
    "targets",
    "receptions",
    "receiving_yards",
    "receiving_tds",
]

# Leaderboard / trend table columns for box-score stats (nullable by position)
LEADERBOARD_VOLUME_COLUMNS = [
    {"name": "Pass Att", "id": "pass_attempts", "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Cmp", "id": "completions", "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Pass Yds", "id": "passing_yards", "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Pass TD", "id": "passing_tds", "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "INT", "id": "interceptions", "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Car", "id": "carries", "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Rush Yds", "id": "rushing_yards", "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Rush TD", "id": "rushing_tds", "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Tgt", "id": "targets", "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Rec", "id": "receptions", "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Rec Yds", "id": "receiving_yards", "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Rec TD", "id": "receiving_tds", "type": "numeric", "format": {"specifier": ".0f"}},
]

_LEADERBOARD_VOLUME_BY_ID = {col["id"]: col for col in LEADERBOARD_VOLUME_COLUMNS}

# Clickable in tables — opens player detail (see callbacks + PLAYER_NAME_TABLE_STYLES).
PLAYER_NAME_COLUMN = {"name": "Player", "id": "player_name"}

LEADERBOARD_CORE_COLUMNS = [
    PLAYER_NAME_COLUMN,
    {"name": "Team", "id": "team"},
    {"name": "Season", "id": "season", "type": "numeric"},
]

# Sent with table rows but not shown as columns (player detail, drill-down)
LEADERBOARD_ROW_HIDDEN_FIELDS = [
    "player_id",
    "position",
    "primary_metric",
    "primary_value",
    "primary_expected",
    "composite_z",
    "role_z",
    "efficiency_z",
    "efficiency_z_raw",
    "efficiency_age_z_adjustment",
    "production_z",
    "flag",
    "focus_metric",
]

LEADERBOARD_COMPOSITE_FOCUS_COLUMNS = [
    {"name": "Age", "id": "player_age", "type": "numeric", "format": {"specifier": ".0f"}},
    {"name": "Experience", "id": "years_exp", "type": "numeric", "format": {"specifier": ".0f"}},
    {
        "name": "Prod Percentile",
        "id": "composite_percentile",
        "type": "numeric",
        "format": {"specifier": ".1f"},
    },
    {"name": "Flag", "id": "flag_label"},
]

# Backward-compatible alias
LEADERBOARD_FOCUS_COLUMNS = LEADERBOARD_COMPOSITE_FOCUS_COLUMNS


def leaderboard_focus_columns(metric_view: str | None = None) -> list[dict]:
    """Focus columns for the selected v12 score view (percentile only, no raw z on table)."""
    view = normalize_score_view(metric_view)
    bio_cols = [
        {"name": "Age", "id": "player_age", "type": "numeric", "format": {"specifier": ".0f"}},
        {"name": "Experience", "id": "years_exp", "type": "numeric", "format": {"specifier": ".0f"}},
    ]
    flag_col = {"name": "Flag", "id": "flag_label"}
    percentile_cols = {
        METRIC_VIEW_PRODUCTION: (
            "Prod Percentile",
            "composite_percentile",
        ),
        METRIC_VIEW_ROLE: ("Role Percentile", "focus_percentile"),
        METRIC_VIEW_EFFICIENCY: ("Eff Percentile", "focus_percentile"),
    }
    pct_name, pct_id = percentile_cols[view]
    return [
        *bio_cols,
        {
            "name": pct_name,
            "id": pct_id,
            "type": "numeric",
            "format": {"specifier": ".1f"},
        },
        flag_col,
    ]


def leaderboard_columns_for_position(
    position: str,
    metric_view: str | None = None,
) -> list[dict]:
    """DataTable columns for one position — volume stats only, no blank N/A columns."""
    from components.team_logos import TEAM_LOGO_COLUMN

    field_ids = [field_id for field_id, _ in VOLUME_FIELDS_BY_POSITION.get(position, [])]
    volume_cols = [
        _LEADERBOARD_VOLUME_BY_ID[field_id]
        for field_id in field_ids
        if field_id in _LEADERBOARD_VOLUME_BY_ID
    ]
    return [TEAM_LOGO_COLUMN, *LEADERBOARD_CORE_COLUMNS, *volume_cols, *leaderboard_focus_columns(metric_view)]


# Player detail trend chart — per-week box-score lines (not cumulative regression metrics)
PLAYER_WEEKLY_YARD_STATS = frozenset({"passing_yards", "rushing_yards", "receiving_yards"})
PLAYER_WEEKLY_CHART_SERIES: dict[str, list[tuple[str, str]]] = {
    "QB": [
        ("passing_yards", "Pass Yds"),
        ("rushing_yards", "Rush Yds"),
    ],
    "WR": [
        ("receiving_yards", "Rec Yds"),
        ("receptions", "Catches"),
    ],
    "TE": [
        ("receiving_yards", "Rec Yds"),
        ("receptions", "Catches"),
    ],
    "RB": [
        ("carries", "Carries"),
        ("rushing_yards", "Rush Yds"),
        ("receptions", "Rec"),
        ("receiving_yards", "Rec Yds"),
    ],
}


VOLUME_FIELDS_BY_POSITION: dict[str, list[tuple[str, str]]] = {
    "QB": [
        ("pass_attempts", "Pass attempts"),
        ("completions", "Completions"),
        ("passing_yards", "Passing yards"),
        ("passing_tds", "Pass TD"),
        ("interceptions", "Interceptions"),
        ("dropbacks", "Dropbacks"),
    ],
    "WR": [
        ("targets", "Targets"),
        ("receptions", "Receptions"),
        ("receiving_yards", "Receiving yards"),
        ("receiving_tds", "Receiving TD"),
    ],
    "TE": [
        ("targets", "Targets"),
        ("receptions", "Receptions"),
        ("receiving_yards", "Receiving yards"),
        ("receiving_tds", "Receiving TD"),
    ],
    "RB": [
        ("carries", "Carries"),
        ("rushing_yards", "Rushing yards"),
        ("rushing_tds", "Rushing TD"),
        ("targets", "Targets"),
        ("receptions", "Receptions"),
        ("receiving_yards", "Receiving yards"),
    ],
}

# --- Metric definitions (PRD §5) ---
METRIC_DEFINITIONS = {
    "QB": {
        "qb_cpoe": {
            "name": "Completion % Over Expected",
            "weight_category": "process",
            "primary": True,
        },
        "qb_completion_percentage_above_expectation": {
            "name": "Completion % Above Expectation (NGS)",
            "weight_category": "process",
            "pushes_toward_lower_z": True,
            "include_in_composite": False,
            "primary": False,
        },
        "qb_epa_per_play": {
            "name": "EPA per Play",
            "weight_category": "process",
            "include_in_composite": True,
            "pushes_toward_lower_z": False,
            "primary": False,
        },
        "qb_td_rate": {
            "name": "TD Rate vs. Opportunity",
            "weight_category": "td_rate",
            "primary": False,
        },
        "qb_adot": {
            "name": "Air Depth of Target",
            "weight_category": "default",
            "pushes_toward_lower_z": True,
            "primary": False,
        },
        "qb_pressure_rate": {
            "name": "Pressure Rate",
            "weight_category": "pressure",
            # If this stat is high, it should push the player's z-score downward
            # (i.e., toward a breakout / regressing-up composite).
            "pushes_toward_lower_z": True,
            "primary": False,
        },
        "age_curve": {
            "name": "Age Curve",
            "weight_category": "age_curve",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_dropbacks": {
            "name": "Dropbacks",
            "source_col": "dropbacks",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_pass_att": {
            "name": "Pass Attempts",
            "source_col": "pass_attempts",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_completions": {
            "name": "Completions",
            "source_col": "completions",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_pass_yds": {
            "name": "Passing Yards",
            "source_col": "passing_yards",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_pass_tds": {
            "name": "Passing TD",
            "source_col": "passing_tds",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_interceptions": {
            "name": "Interceptions",
            "source_col": "interceptions",
            "weight_category": "volume",
            "include_in_composite": False,
            "pushes_toward_lower_z": True,
            "primary": False,
        },
    },
    "WR": {
        "recv_target_share": {
            "name": "Target Share",
            "weight_category": "target_share",
            "primary": True,
        },
        "opportunity_share": {
            "name": "Opportunity Share",
            "weight_category": "target_share",
            "include_in_composite": False,
            "primary": False,
        },
        "recv_ypt": {
            "name": "Yards Per Target",
            "weight_category": "yards_per_target",
            "include_in_composite": False,
            "primary": False,
        },
        "recv_yac_oe": {
            "name": "YAC Over Expected",
            "weight_category": "process",
            "include_in_composite": False,
            "primary": False,
        },
        "recv_separation": {
            "name": "Average Separation",
            "weight_category": "process",
            "include_in_composite": False,
            "primary": False,
        },
        "recv_catch_rate_oe": {
            "name": "Catch Rate Over Expected",
            "weight_category": "process",
            "include_in_composite": False,
            "primary": False,
        },
        "recv_td_share": {
            "name": "TD Share vs. Opportunity",
            "weight_category": "td_rate",
            "primary": False,
        },
        "age_curve": {
            "name": "Age Curve",
            "weight_category": "age_curve",
            "primary": False,
        },
        "vol_targets": {
            "name": "Targets",
            "source_col": "targets",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_air_yards_share": {
            "name": "Air Yards Share",
            "source_col": "air_yards_share",
            "weight_category": "target_share",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_receptions": {
            "name": "Receptions",
            "source_col": "receptions",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_rec_yds": {
            "name": "Receiving Yards",
            "source_col": "receiving_yards",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_rec_tds": {
            "name": "Receiving TD",
            "source_col": "receiving_tds",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
    },
    "TE": {
        "recv_target_share": {
            "name": "Target Share",
            "weight_category": "target_share",
            "primary": True,
        },
        "opportunity_share": {
            "name": "Opportunity Share",
            "weight_category": "target_share",
            "include_in_composite": False,
            "primary": False,
        },
        "recv_ypt": {
            "name": "Yards Per Target",
            "weight_category": "yards_per_target",
            "include_in_composite": False,
            "primary": False,
        },
        "recv_yac_oe": {
            "name": "YAC Over Expected",
            "weight_category": "process",
            "include_in_composite": False,
            "primary": False,
        },
        "recv_separation": {
            "name": "Average Separation",
            "weight_category": "process",
            "include_in_composite": False,
            "primary": False,
        },
        "recv_catch_rate_oe": {
            "name": "Catch Rate Over Expected",
            "weight_category": "process",
            "include_in_composite": False,
            "primary": False,
        },
        "recv_td_share": {
            "name": "TD Share vs. Opportunity",
            "weight_category": "td_rate",
            "primary": False,
        },
        "age_curve": {
            "name": "Age Curve",
            "weight_category": "age_curve",
            "primary": False,
        },
        "vol_targets": {
            "name": "Targets",
            "source_col": "targets",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_air_yards_share": {
            "name": "Air Yards Share",
            "source_col": "air_yards_share",
            "weight_category": "target_share",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_receptions": {
            "name": "Receptions",
            "source_col": "receptions",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_rec_yds": {
            "name": "Receiving Yards",
            "source_col": "receiving_yards",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_rec_tds": {
            "name": "Receiving TD",
            "source_col": "receiving_tds",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
    },
    "RB": {
        "rb_ryoe": {
            "name": "Rushing Yards Over Expected",
            "weight_category": "process",
            "primary": True,
        },
        "rb_avg_time_to_los": {
            "name": "Avg Time to LOS (NGS)",
            "weight_category": "default",
            # If this is slower, it should push the oriented z lower.
            "pushes_toward_lower_z": True,
            "include_in_composite": False,
            "primary": False,
        },
        "rb_efficiency": {
            "name": "Efficiency (NGS)",
            "weight_category": "rb_efficiency",
            "include_in_composite": False,
            "primary": False,
        },
        "rb_scrimmage_yards": {
            "name": "Scrimmage Yards",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
        "rb_total_tds": {
            "name": "Total TD",
            "weight_category": "td_rate",
            "include_in_composite": False,
            "primary": False,
        },
        "rb_target_share": {
            "name": "Target Share",
            "weight_category": "target_share",
            "primary": False,
        },
        "opportunity_share": {
            "name": "Opportunity Share",
            "weight_category": "target_share",
            "include_in_composite": False,
            "primary": False,
        },
        "rb_td_rate": {
            "name": "TD Rate vs. Opportunity",
            "weight_category": "td_rate",
            "primary": False,
        },
        "rb_breakaway_rate": {
            "name": "Breakaway Run Rate",
            "weight_category": "default",
            "primary": False,
        },
        "age_curve": {
            "name": "Age Curve",
            "weight_category": "age_curve",
            "primary": False,
        },
        "vol_carries": {
            "name": "Carries",
            "source_col": "carries",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_rush_yds": {
            "name": "Rushing Yards",
            "source_col": "rushing_yards",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_rush_tds": {
            "name": "Rushing TD",
            "source_col": "rushing_tds",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_targets": {
            "name": "Targets",
            "source_col": "targets",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_receptions": {
            "name": "Receptions",
            "source_col": "receptions",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
        "vol_rec_yds": {
            "name": "Receiving Yards",
            "source_col": "receiving_yards",
            "weight_category": "volume",
            "include_in_composite": False,
            "primary": False,
        },
    },
}


def normalize_position_filter(value: str | list[str] | None) -> str:
    """Leaderboard position filter is single-select; return a valid position code."""
    if isinstance(value, list):
        value = value[0] if value else None
    if value in POSITIONS:
        return value
    return LEADERBOARD_DEFAULT_POSITION


def score_metric_ids(position: str, score_group: str) -> list[str]:
    """Metric IDs that feed Role / Efficiency / Production z (v12)."""
    return list(SCORE_METRICS.get(position, {}).get(score_group, []))


def score_axis_weights(position: str, score_group: str) -> dict[str, float] | None:
    """Per-metric weights for an axis mean. None → equal-weight mean of score_metric_ids."""
    group = SCORE_AXIS_WEIGHTS.get(position, {}).get(score_group)
    if not group:
        return None
    return dict(group)


def td_luck_metric_ids(position: str) -> list[str]:
    """TD-rate metrics used for TD-luck regression tagging."""
    return list(SCORE_METRICS.get(position, {}).get("td_luck", []))


def metric_in_composite(metric_id: str, position: str) -> bool:
    """v12: legacy composite disabled; scores use SCORE_METRICS groups instead."""
    _ = metric_id, position
    return False


def metric_pushes_toward_lower_z(metric_id: str, position: str) -> bool:
    """
    If True: a higher raw value should result in a lower *oriented* z-score.

    This is the flag the scoring engine uses when orienting “positive z favors
    better play / negative z favors breakout candidate” behavior.
    """
    meta = METRIC_DEFINITIONS.get(position, {}).get(metric_id, {})
    # Backward compatibility: support older configs that used higher_is_worse.
    return bool(meta.get("pushes_toward_lower_z", meta.get("higher_is_worse", False)))


def metric_higher_is_worse(metric_id: str, position: str) -> bool:
    """Backward-compatible alias; prefer metric_pushes_toward_lower_z()."""
    return metric_pushes_toward_lower_z(metric_id, position)


def position_peak_age_range(position: str) -> tuple[int, int]:
    """Inclusive peak-age bounds used for baseline cohort filtering."""
    peak = POSITION_PEAK_AGE.get(position, {})
    return int(peak.get("peak_min", 25)), int(peak.get("peak_max", 28))


def position_productive_age_range(position: str) -> tuple[int, int]:
    """Inclusive productive-age bounds for age-curve scoring."""
    peak = POSITION_PEAK_AGE.get(position, {})
    return int(peak.get("productive_min", 23)), int(peak.get("productive_max", 29))


def age_curve_weight(position: str) -> float:
    """Position scale for efficiency age adjustment (legacy name retained)."""
    return AGE_CURVE_WEIGHT_BY_POSITION.get(position, 0.75)


def efficiency_age_z_adjustment(age_curve_value: float, position: str) -> float:
    """
    Z-score delta applied to efficiency_z from aging.

    age_curve_value < 0 (young) → positive adjustment (boost efficiency z).
    age_curve_value > 0 (old) → negative adjustment.
    In productive window → zero.
    """
    try:
        val = float(age_curve_value)
    except (TypeError, ValueError):
        return 0.0
    if val != val:  # NaN
        return 0.0
    return -val * EFFICIENCY_AGE_Z_PER_YEAR * age_curve_weight(position)


def metric_applies_to_position(metric_id: str, position: str) -> bool:
    return metric_id in METRIC_DEFINITIONS.get(position, {})


# --- PBP columns fetched for metric computation ---
PBP_COLUMNS = [
    "passer_player_id",
    "receiver_player_id",
    "rusher_player_id",
    "passer_player_name",
    "receiver_player_name",
    "rusher_player_name",
    "posteam",
    "season",
    "week",
    "season_type",
    "pass_attempt",
    "complete_pass",
    "incomplete_pass",
    "air_yards",
    "yards_after_catch",
    "yards_gained",
    "pass_touchdown",
    "rush_touchdown",
    "receiving_touchdown",
    "sack",
    "was_pressure",
    "cp",
    "xyac_mean_yardage",
    "epa",
    "yardline_100",
    "rush_attempt",
    "rush",
    "rush_20plus",
    "interception",
]

WEEKLY_COLUMNS = [
    "player_id",
    "player_name",
    "position",
    "recent_team",
    "season",
    "week",
    "completions",
    "attempts",
    "passing_yards",
    "passing_tds",
    "interceptions",
    "carries",
    "rushing_yards",
    "rushing_tds",
    "receptions",
    "targets",
    "receiving_yards",
    "receiving_tds",
    "target_share",
    "air_yards_share",
    "wopr",
    "racr",
]
