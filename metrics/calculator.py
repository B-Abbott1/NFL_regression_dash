"""Z-score computation, metric aggregation, and regression flag logic."""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
import pandas as pd

import config
from metrics.loader import pbp_pass_interception_mask

logger = logging.getLogger(__name__)

RECV_POSITIONS = ("WR", "TE")
ALL_METRIC_IDS = sorted(
    {
        mid
        for pos_defs in config.METRIC_DEFINITIONS.values()
        for mid in pos_defs
    }
)


def compute_z_score(player_value: float, population_values: pd.Series | np.ndarray) -> float:
    """Compute z-score of a player value against a population mean and std."""
    values = pd.Series(population_values).dropna()
    if values.empty or pd.isna(player_value):
        return 0.0
    mean = values.mean()
    std = values.std()
    if std == 0 or np.isnan(std):
        return 0.0
    return float((player_value - mean) / std)


def z_to_percentile(z: float) -> float:
    """Map a z-score to a normal-distribution percentile rank (0–100)."""
    if z is None or pd.isna(z):
        return np.nan
    return float(0.5 * (1.0 + math.erf(float(z) / math.sqrt(2.0))) * 100.0)


def position_cohort_percentile(series: pd.Series, positions: pd.Series) -> pd.Series:
    """Within-position percentile rank (0–100) for a score column; ties averaged."""
    out = pd.Series(np.nan, index=series.index, dtype=float)
    z = pd.to_numeric(series, errors="coerce")
    for position in positions.dropna().unique():
        mask = positions == position
        valid = mask & z.notna()
        if valid.sum() == 0:
            continue
        out.loc[valid] = z.loc[valid].rank(method="average", pct=True) * 100.0
    return out


def _orient_metric_value(
    values: pd.Series,
    metric_id: str,
    position: str,
) -> pd.Series:
    """Flip sign so higher oriented values always mean better performance."""
    if config.metric_pushes_toward_lower_z(metric_id, position):
        return -values
    return values


def _display_expected(oriented_mean: float, metric_id: str, position: str) -> float:
    """Convert oriented baseline mean back to raw scale for UI."""
    if pd.isna(oriented_mean):
        return np.nan
    if config.metric_pushes_toward_lower_z(metric_id, position):
        return float(-oriented_mean)
    return float(oriented_mean)


def _attach_player_ages(
    df: pd.DataFrame,
    df_rosters: pd.DataFrame | None,
) -> pd.DataFrame:
    """Merge season-specific player age from rosters onto player-season rows."""
    if df.empty:
        return df
    out = df.drop(columns=["player_age"], errors="ignore")
    if df_rosters is None or df_rosters.empty:
        out["player_age"] = np.nan
        return out

    parts: list[pd.DataFrame] = []
    for season in out["season"].dropna().unique():
        chunk = out[out["season"] == season].copy()
        bio = _player_bio_map(df_rosters, int(season))
        if bio.empty:
            chunk["player_age"] = np.nan
        else:
            chunk = chunk.merge(bio[["player_id", "player_age"]], on="player_id", how="left")
        parts.append(chunk)
    return pd.concat(parts, ignore_index=True)


def _age_curve_value(age: float, position: str) -> float:
    """
    Signed years outside the position productive-age window.

    Negative = below productive_min (young upside), positive = above productive_max
    (decline risk), zero = in window.
    """
    if age is None or pd.isna(age):
        return np.nan
    prod_min, prod_max = config.position_productive_age_range(position)
    age_f = float(age)
    if age_f < prod_min:
        return age_f - prod_min
    if age_f > prod_max:
        return age_f - prod_max
    return 0.0


def _peak_age_position_stats(
    df: pd.DataFrame,
    value_col: str,
    metric_id: str,
) -> pd.DataFrame:
    """
    Mean/std by position for each target season using prior-season players.

    Performance metrics: prior-season peak-age cohort. Age curve: full position pool.
    Stats are computed on direction-oriented values (higher = better).
    """
    use_full_pool = metric_id == "age_curve"
    parts: list[pd.DataFrame] = []
    for target_season in df["season"].dropna().unique():
        prior_season = config.z_score_baseline_season(int(target_season))
        prior = df[df["season"] == prior_season].copy()
        if prior.empty or (not use_full_pool and "player_age" not in prior.columns):
            continue

        rows: list[dict[str, Any]] = []
        for position in config.POSITIONS:
            if not config.metric_applies_to_position(metric_id, position):
                continue
            if use_full_pool:
                cohort = prior[prior["position"] == position]
            else:
                peak_min, peak_max = config.position_peak_age_range(position)
                cohort = prior[
                    (prior["position"] == position)
                    & prior["player_age"].notna()
                    & (prior["player_age"] >= peak_min)
                    & (prior["player_age"] <= peak_max)
                ]
                if cohort.empty:
                    cohort = prior[prior["position"] == position]
                    if not cohort.empty:
                        logger.debug(
                            "Peak-age cohort empty for %s %s; using full position pool",
                            position,
                            metric_id,
                        )
            if cohort.empty or value_col not in cohort.columns:
                rows.append(
                    {
                        "position": position,
                        "oriented_mean": np.nan,
                        "oriented_std": np.nan,
                    }
                )
                continue
            oriented = _orient_metric_value(cohort[value_col], metric_id, position).dropna()
            if oriented.empty:
                rows.append(
                    {
                        "position": position,
                        "oriented_mean": np.nan,
                        "oriented_std": np.nan,
                    }
                )
                continue
            rows.append(
                {
                    "position": position,
                    "oriented_mean": float(oriented.mean()),
                    "oriented_std": float(oriented.std()),
                }
            )
        if not rows:
            continue
        grouped = pd.DataFrame(rows)
        grouped["season"] = int(target_season)
        parts.append(grouped)

    if not parts:
        return pd.DataFrame(columns=["season", "position", "oriented_mean", "oriented_std"])
    return pd.concat(parts, ignore_index=True)


def flag_regression(z_score: float) -> str:
    """Single-metric z threshold tag (v12 names)."""
    if z_score >= config.REGRESSION_Z_THRESHOLD:
        return "regress_negative"
    if z_score <= -config.REGRESSION_Z_THRESHOLD:
        return "positive_outlook"
    return "neutral"


def apply_flag_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize v12 tags and attach human-readable flag_label."""
    if df.empty or "flag" not in df.columns:
        return df
    out = df.copy()
    out["flag"] = out["flag"].apply(config.normalize_player_flag)
    out["flag_label"] = out["flag"].map(config.FLAG_LABELS).fillna(config.FLAG_LABELS["neutral"])
    return out


def get_metric_weight(metric_id: str, position: str) -> float:
    """Look up composite weight for a metric."""
    defs = config.METRIC_DEFINITIONS.get(position, {})
    meta = defs.get(metric_id, {})
    category = meta.get("weight_category", "default")
    if category == "age_curve":
        return config.age_curve_weight(position)
    return config.METRIC_WEIGHTS.get(category, config.METRIC_WEIGHTS["default"])


def compute_composite_z(metric_z_scores: dict[str, float], position: str) -> float:
    """Legacy weighted composite; v12 uses compute_score_z / production_z for ranking."""
    prod = compute_score_z(metric_z_scores, config.score_metric_ids(position, "production"))
    if prod != 0.0 or config.score_metric_ids(position, "production"):
        return prod
    if not metric_z_scores:
        return 0.0
    weighted_sum = 0.0
    weight_total = 0.0
    for metric_id, z in metric_z_scores.items():
        if pd.isna(z) or not config.metric_in_composite(metric_id, position):
            continue
        weight = get_metric_weight(metric_id, position)
        weighted_sum += z * weight
        weight_total += weight
    if weight_total == 0:
        return 0.0
    return weighted_sum / weight_total


def compute_score_z(
    metric_z_scores: dict[str, float],
    metric_ids: list[str],
    *,
    position: str | None = None,
    score_group: str | None = None,
) -> float:
    """
    Mean z-score for a score axis (role / efficiency / production).

    Uses SCORE_AXIS_WEIGHTS when configured; renormalizes if some metrics are missing.
    """
    weights = (
        config.score_axis_weights(position, score_group)
        if position and score_group
        else None
    )
    if weights:
        weighted_sum = 0.0
        weight_total = 0.0
        for mid, weight in weights.items():
            if mid not in metric_ids:
                continue
            z = metric_z_scores.get(mid)
            if z is None or pd.isna(z):
                continue
            weighted_sum += float(z) * weight
            weight_total += weight
        if weight_total > 0:
            return weighted_sum / weight_total
        return 0.0

    values = [
        float(metric_z_scores[mid])
        for mid in metric_ids
        if mid in metric_z_scores and pd.notna(metric_z_scores[mid])
    ]
    if not values:
        return 0.0
    return float(np.mean(values))


def compute_axis_scores(
    metric_z_scores: dict[str, float],
    position: str,
    *,
    age_curve_value: float | None = None,
) -> dict[str, float]:
    """Role, efficiency (age-adjusted), and production z for one player."""
    role_z = compute_score_z(
        metric_z_scores,
        config.score_metric_ids(position, "role"),
        position=position,
        score_group="role",
    )
    efficiency_z_raw = compute_score_z(
        metric_z_scores,
        config.score_metric_ids(position, "efficiency"),
        position=position,
        score_group="efficiency",
    )
    age_adj = config.efficiency_age_z_adjustment(age_curve_value, position)
    return {
        "role_z": role_z,
        "efficiency_z_raw": efficiency_z_raw,
        "efficiency_age_z_adjustment": age_adj,
        "efficiency_z": efficiency_z_raw + age_adj,
        "production_z": compute_score_z(
            metric_z_scores,
            config.score_metric_ids(position, "production"),
            position=position,
            score_group="production",
        ),
    }


def _td_luck_triggered(
    row: pd.Series,
    position: str,
    prod_z: float,
    eff_z: float,
) -> bool:
    """High production with elevated TD-rate z and weak efficiency."""
    if not _tag_axis_ge(prod_z, config.TAG_REGRESS_MIN_PRODUCTION_Z):
        return False
    if not _tag_axis_le(eff_z, config.TAG_TD_LUCK_MAX_EFFICIENCY_Z):
        return False
    for mid in config.td_luck_metric_ids(position):
        z = row.get(f"{mid}_z", np.nan)
        if pd.notna(z) and _tag_axis_ge(float(z), config.TAG_TD_LUCK_MIN_TD_RATE_Z):
            return True
    return False


def _tag_axis_ge(z: float, cutoff: float) -> bool:
    """Axis z at or above cutoff (tolerant of float rounding from JSON/store round-trip)."""
    return float(z) >= float(cutoff) - 1e-6


def _tag_axis_le(z: float, cutoff: float) -> bool:
    return float(z) <= float(cutoff) + 1e-6


def assign_player_tag(
    role_z: float,
    efficiency_z: float,
    production_z: float,
    *,
    volume_qualified: bool,
) -> str:
    """
    Player tag from v12 axis z-scores (cutoffs in config.TAG_* constants).

    Age affects tags only via age-adjusted efficiency_z, not as a gate.
    Priority: star > regress_negative > breakout > positive_outlook > neutral.
    """
    if (
        _tag_axis_ge(production_z, config.TAG_STAR_MIN_PRODUCTION_Z)
        and _tag_axis_ge(efficiency_z, config.TAG_STAR_MIN_EFFICIENCY_Z)
    ):
        return "star"
    if (
        _tag_axis_ge(production_z, config.TAG_REGRESS_MIN_PRODUCTION_Z)
        and _tag_axis_le(efficiency_z, config.TAG_REGRESS_MAX_EFFICIENCY_Z)
    ) or (
        _tag_axis_ge(role_z, config.TAG_REGRESS_MIN_ROLE_Z)
        and _tag_axis_le(production_z, config.TAG_REGRESS_MAX_PRODUCTION_Z)
    ):
        return "regress_negative"
    if (
        _tag_axis_le(role_z, config.TAG_BREAKOUT_MAX_ROLE_Z)
        and _tag_axis_ge(efficiency_z, config.TAG_BREAKOUT_MIN_EFFICIENCY_Z)
        and volume_qualified
    ):
        return "breakout"
    if (
        _tag_axis_le(production_z, config.TAG_OUTLOOK_MAX_PRODUCTION_Z)
        and _tag_axis_ge(efficiency_z, config.TAG_OUTLOOK_MIN_EFFICIENCY_Z)
    ):
        return "positive_outlook"
    return "neutral"


def assign_player_tag_from_row(row: pd.Series) -> str:
    """Tag helper when TD-luck and axis z columns are on the row."""
    position = row.get("position", "")
    role_z = float(pd.to_numeric(row.get("role_z", 0.0), errors="coerce") or 0.0)
    eff_z = float(pd.to_numeric(row.get("efficiency_z", 0.0), errors="coerce") or 0.0)
    prod_z = float(pd.to_numeric(row.get("production_z", 0.0), errors="coerce") or 0.0)

    tag = assign_player_tag(
        role_z,
        eff_z,
        prod_z,
        volume_qualified=bool(row.get("_volume_qualified", is_qualified(row))),
    )
    if tag == "neutral" and _td_luck_triggered(row, position, prod_z, eff_z):
        return "regress_negative"
    return tag


def is_qualified(row: pd.Series) -> bool:
    """Check if a player-season meets minimum volume thresholds."""
    position = row.get("position")
    if position == "QB":
        return (row.get("dropbacks") or 0) >= config.QUALIFY_MIN_DROPBACKS_QB
    if position in RECV_POSITIONS:
        return (row.get("targets") or 0) >= config.QUALIFY_MIN_TARGETS_RECV
    if position == "RB":
        return (row.get("carries") or 0) >= config.QUALIFY_MIN_CARRIES_RB
    return False


def _primary_metric_id(position: str) -> str:
    defs = config.METRIC_DEFINITIONS.get(position, {})
    for mid, meta in defs.items():
        if meta.get("primary"):
            return mid
    return next(iter(defs), "")


def _rush_col(pbp: pd.DataFrame) -> str:
    return "rush_attempt" if "rush_attempt" in pbp.columns else "rush"


def _merge_qb_weekly_volumes(
    out: pd.DataFrame, weekly: pd.DataFrame, season: int
) -> pd.DataFrame:
    """Fill QB counting stats from weekly when PBP omits them (e.g. interceptions)."""
    if weekly.empty or out.empty:
        return out
    wk = weekly[(weekly["season"] == season) & (weekly["position"] == "QB")].copy()
    if wk.empty:
        return out
    vol = wk.groupby("player_id", as_index=False).agg(
        completions_wk=("completions", "sum"),
        passing_yards_wk=("passing_yards", "sum"),
        passing_tds_wk=("passing_tds", "sum"),
        interceptions_wk=("interceptions", "sum"),
        pass_attempts_wk=("attempts", "sum"),
    )
    merged = out.merge(vol, on="player_id", how="left")
    for pbp_col, wk_col in (
        ("completions", "completions_wk"),
        ("passing_yards", "passing_yards_wk"),
        ("passing_tds", "passing_tds_wk"),
        ("interceptions", "interceptions_wk"),
        ("pass_attempts", "pass_attempts_wk"),
    ):
        if wk_col in merged.columns:
            if pbp_col not in merged.columns:
                merged[pbp_col] = merged[wk_col]
            else:
                merged[pbp_col] = merged[pbp_col].combine_first(merged[wk_col])
    drop_cols = [c for c in merged.columns if c.endswith("_wk")]
    return merged.drop(columns=drop_cols, errors="ignore")


def _compute_qb_metrics(
    pbp: pd.DataFrame,
    ngs_passing: pd.DataFrame,
    weekly: pd.DataFrame,
    season: int,
) -> pd.DataFrame:
    """Season-level QB metrics for one season."""
    df = pbp[(pbp["season"] == season) & pbp["passer_player_id"].notna()].copy()
    if df.empty:
        return pd.DataFrame()

    pass_att = df[df["pass_attempt"] == 1]
    sacks = df[df["sack"] == 1]

    dropbacks = (
        pass_att.groupby("passer_player_id", as_index=False)
        .agg(
            dropbacks=("pass_attempt", "count"),
            player_name=("passer_player_name", "last"),
            team=("posteam", "last"),
            pass_tds=("pass_touchdown", "sum"),
            air_yards=("air_yards", "sum"),
            pass_attempts=("pass_attempt", "sum"),
            completions=("complete_pass", "sum"),
            passing_yards=("yards_gained", "sum"),
            pressures=("was_pressure", "sum"),
            week_end=("week", "max"),
        )
    )
    if "interception" in pass_att.columns or "interception_player_id" in pass_att.columns:
        int_mask = pbp_pass_interception_mask(pass_att)
        ints = (
            pass_att.assign(_is_int=int_mask.astype(int))
            .groupby("passer_player_id")["_is_int"]
            .sum()
            .reset_index(name="interceptions")
        )
    else:
        ints = pd.DataFrame(columns=["passer_player_id", "interceptions"])
    sack_ct = sacks.groupby("passer_player_id", as_index=False).agg(sacks=("sack", "sum"))
    out = dropbacks.merge(sack_ct, on="passer_player_id", how="left")
    if not ints.empty:
        out = out.merge(ints, on="passer_player_id", how="left")
    out["sacks"] = out["sacks"].fillna(0)
    out["dropbacks"] = out["dropbacks"] + out["sacks"]
    out["passing_tds"] = out["pass_tds"]

    cp_plays = pass_att[pass_att["cp"].notna()].copy()
    if not cp_plays.empty:
        cpoe = (
            cp_plays.groupby("passer_player_id")
            .apply(
                lambda g: (g["complete_pass"] - g["cp"]).mean(),
                include_groups=False,
            )
            .reset_index(name="qb_cpoe_value")
        )
        out = out.merge(cpoe, left_on="passer_player_id", right_on="passer_player_id", how="left")

    if not ngs_passing.empty:
        ngs = ngs_passing[ngs_passing["season"] == season].copy()
        if "player_gsis_id" in ngs.columns and "completion_percentage_above_expectation" in ngs.columns:
            ngs_agg = (
                ngs.groupby("player_gsis_id")
                .apply(
                    lambda g: np.average(
                        g["completion_percentage_above_expectation"],
                        weights=g["attempts"].clip(lower=1),
                    )
                    if g["attempts"].sum() > 0
                    else np.nan,
                    include_groups=False,
                )
                .reset_index(name="ngs_cpoe")
            )
            out = out.merge(
                ngs_agg,
                left_on="passer_player_id",
                right_on="player_gsis_id",
                how="left",
            )
            # Keep an explicit NGS-only CPOE-style metric for analysis.
            out["qb_completion_percentage_above_expectation_value"] = out.get("ngs_cpoe")
            if "qb_cpoe_value" not in out.columns:
                out["qb_cpoe_value"] = np.nan
            out["qb_cpoe_value"] = out["ngs_cpoe"].combine_first(out["qb_cpoe_value"])
        else:
            out["qb_completion_percentage_above_expectation_value"] = np.nan
    else:
        out["qb_completion_percentage_above_expectation_value"] = np.nan

    out["qb_td_rate_value"] = out["pass_tds"] / out["dropbacks"].replace(0, np.nan)
    out["qb_adot_value"] = out["air_yards"] / out["pass_attempts"].replace(0, np.nan)
    out["qb_pressure_rate_value"] = out["pressures"] / out["dropbacks"].replace(0, np.nan)
    if "epa" in df.columns:
        epa = (
            df.groupby("passer_player_id", as_index=False)["epa"]
            .mean()
            .rename(columns={"epa": "qb_epa_per_play_value"})
        )
        out = out.merge(epa, on="passer_player_id", how="left")
    else:
        out["qb_epa_per_play_value"] = np.nan

    out = out.rename(columns={"passer_player_id": "player_id"})
    out["position"] = "QB"
    out["season"] = season
    out = _merge_qb_weekly_volumes(out, weekly, season)
    return out


def _compute_recv_metrics(
    pbp: pd.DataFrame,
    weekly: pd.DataFrame,
    ngs_receiving: pd.DataFrame,
    season: int,
) -> pd.DataFrame:
    """Season-level WR/TE metrics for one season."""
    wk = weekly[
        (weekly["season"] == season) & weekly["position"].isin(RECV_POSITIONS)
    ].copy()
    if wk.empty:
        return pd.DataFrame()

    season_agg = (
        wk.groupby(["player_id", "player_name", "position", "recent_team"], as_index=False)
        .agg(
            targets=("targets", "sum"),
            receptions=("receptions", "sum"),
            receiving_yards=("receiving_yards", "sum"),
            receiving_tds=("receiving_tds", "sum"),
            week_end=("week", "max"),
        )
        .rename(columns={"recent_team": "team"})
    )
    season_agg["recv_target_share_value"] = (
        wk.groupby("player_id")["target_share"].mean().reindex(season_agg["player_id"]).values
    )
    team_targets = wk.groupby("recent_team")["targets"].sum(min_count=1)
    season_agg["opportunity_share_value"] = season_agg.apply(
        lambda r: (
            np.nan
            if pd.isna(team_targets.get(r["team"], np.nan)) or team_targets.get(r["team"], 0) == 0
            else r["targets"] / team_targets.get(r["team"])
        ),
        axis=1,
    )
    season_agg["recv_ypt_value"] = (
        season_agg["receiving_yards"] / season_agg["targets"].replace(0, np.nan)
    )

    recv_pbp = pbp[
        (pbp["season"] == season)
        & pbp["receiver_player_id"].notna()
        & (pbp["pass_attempt"] == 1)
    ].copy()
    if not recv_pbp.empty:
        yac = recv_pbp[recv_pbp["xyac_mean_yardage"].notna()].copy()
        if not yac.empty:
            yac["yac_oe"] = yac["yards_after_catch"] - yac["xyac_mean_yardage"]
            yac_agg = yac.groupby("receiver_player_id")["yac_oe"].mean().reset_index()
            yac_agg.columns = ["player_id", "recv_yac_oe_value"]
            season_agg = season_agg.merge(yac_agg, on="player_id", how="left")

        cp_tgt = recv_pbp[recv_pbp["cp"].notna()].copy()
        if not cp_tgt.empty:
            catch = (
                cp_tgt.groupby("receiver_player_id")
                .agg(receptions=("complete_pass", "sum"), targets=("pass_attempt", "count"), exp_cp=("cp", "mean"))
                .reset_index()
            )
            catch["recv_catch_rate_oe_value"] = (
                catch["receptions"] / catch["targets"].replace(0, np.nan) - catch["exp_cp"]
            )
            season_agg = season_agg.merge(
                catch[["receiver_player_id", "recv_catch_rate_oe_value"]].rename(
                    columns={"receiver_player_id": "player_id"}
                ),
                on="player_id",
                how="left",
            )

        if "red_zone" in recv_pbp.columns:
            rz = recv_pbp[recv_pbp["red_zone"] == 1]
        elif "yardline_100" in recv_pbp.columns:
            rz = recv_pbp[recv_pbp["yardline_100"] <= 20]
        else:
            rz = pd.DataFrame()
        if not rz.empty:
            rz_agg = (
                rz.groupby("receiver_player_id")
                .agg(rz_targets=("pass_attempt", "count"), rz_tds=("pass_touchdown", "sum"))
                .reset_index()
            )
            rz_agg["recv_td_share_value"] = rz_agg["rz_tds"] / rz_agg["rz_targets"].replace(0, np.nan)
            season_agg = season_agg.merge(
                rz_agg[["receiver_player_id", "recv_td_share_value"]].rename(
                    columns={"receiver_player_id": "player_id"}
                ),
                on="player_id",
                how="left",
            )

    if not ngs_receiving.empty:
        ngs = ngs_receiving[ngs_receiving["season"] == season].copy()
        if "avg_separation" in ngs.columns:
            sep = (
                ngs.groupby("player_gsis_id")
                .apply(
                    lambda g: np.average(g["avg_separation"], weights=g["targets"].clip(lower=1))
                    if g["targets"].sum() > 0
                    else np.nan,
                    include_groups=False,
                )
                .reset_index(name="recv_separation_value")
            )
            sep.columns = ["player_id", "recv_separation_value"]
            season_agg = season_agg.merge(sep, on="player_id", how="left")

    season_agg["season"] = season
    return season_agg


def _compute_rb_metrics(
    pbp: pd.DataFrame,
    weekly: pd.DataFrame,
    ngs_rushing: pd.DataFrame,
    season: int,
) -> pd.DataFrame:
    """Season-level RB metrics for one season."""
    wk = weekly[(weekly["season"] == season) & (weekly["position"] == "RB")].copy()
    if wk.empty:
        return pd.DataFrame()

    season_agg = (
        wk.groupby(["player_id", "player_name", "position", "recent_team"], as_index=False)
        .agg(
            targets=("targets", "sum"),
            receptions=("receptions", "sum"),
            receiving_yards=("receiving_yards", "sum"),
            carries=("carries", "sum"),
            rushing_yards=("rushing_yards", "sum"),
            rushing_tds=("rushing_tds", "sum"),
            week_end=("week", "max"),
        )
        .rename(columns={"recent_team": "team"})
    )
    season_agg["rb_target_share_value"] = (
        wk.groupby("player_id")["target_share"].mean().reindex(season_agg["player_id"]).values
    )
    season_agg["rb_td_rate_value"] = season_agg["rushing_tds"] / season_agg["carries"].replace(0, np.nan)
    season_weekly = weekly[weekly["season"] == season].copy()
    if not season_weekly.empty and "recent_team" in season_weekly.columns:
        team_touches = (
            season_weekly.groupby("recent_team")
            .apply(
                lambda g: g.get("targets", pd.Series(dtype=float)).fillna(0).sum()
                + g.get("carries", pd.Series(dtype=float)).fillna(0).sum(),
                include_groups=False,
            )
            .to_dict()
        )
    else:
        team_touches = {}
    season_agg["opportunity_share_value"] = season_agg.apply(
        lambda r: (
            np.nan
            if pd.isna(team_touches.get(r["team"], np.nan)) or team_touches.get(r["team"], 0) == 0
            else (r["targets"] + r["carries"]) / team_touches.get(r["team"])
        ),
        axis=1,
    )

    rush_col = _rush_col(pbp)
    rush_pbp = pbp[
        (pbp["season"] == season)
        & pbp["rusher_player_id"].notna()
        & (pbp[rush_col] == 1)
    ].copy()
    if not rush_pbp.empty and "rush_20plus" in rush_pbp.columns:
        boom = (
            rush_pbp.groupby("rusher_player_id")
            .agg(booms=("rush_20plus", "sum"), carries=(rush_col, "sum"))
            .reset_index()
        )
        boom["rb_breakaway_rate_value"] = boom["booms"] / boom["carries"].replace(0, np.nan)
        season_agg = season_agg.merge(
            boom[["rusher_player_id", "rb_breakaway_rate_value"]].rename(
                columns={"rusher_player_id": "player_id"}
            ),
            on="player_id",
            how="left",
        )

    if not ngs_rushing.empty:
        ngs = ngs_rushing[ngs_rushing["season"] == season].copy()
        if "rush_yards_over_expected" in ngs.columns:
            ryoe = (
                ngs.groupby("player_gsis_id")["rush_yards_over_expected"]
                .sum()
                .reset_index()
            )
            ryoe.columns = ["player_id", "rb_ryoe_value"]
            season_agg = season_agg.merge(ryoe, on="player_id", how="left")

        # Add additional NGS-only season metrics for analysis.
        if "avg_time_to_los" in ngs.columns:
            atl = (
                ngs.groupby("player_gsis_id")
                .apply(
                    lambda g: np.average(
                        g["avg_time_to_los"],
                        weights=g.get("rush_attempts", pd.Series([1] * len(g))).clip(lower=1),
                    )
                    if g.get("rush_attempts", pd.Series([0] * len(g))).sum() > 0
                    else np.nan,
                    include_groups=False,
                )
                .reset_index(name="rb_avg_time_to_los_value")
            )
            atl.columns = ["player_id", "rb_avg_time_to_los_value"]
            season_agg = season_agg.merge(atl, on="player_id", how="left")

        if "efficiency" in ngs.columns:
            eff = (
                ngs.groupby("player_gsis_id")
                .apply(
                    lambda g: np.average(
                        g["efficiency"],
                        weights=g.get("rush_attempts", pd.Series([1] * len(g))).clip(lower=1),
                    )
                    if g.get("rush_attempts", pd.Series([0] * len(g))).sum() > 0
                    else np.nan,
                    include_groups=False,
                )
                .reset_index(name="rb_efficiency_value")
            )
            eff.columns = ["player_id", "rb_efficiency_value"]
            season_agg = season_agg.merge(eff, on="player_id", how="left")

    season_agg["season"] = season
    return season_agg


def compute_all_season_metrics(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build one row per qualified player-season with metric value columns."""
    pbp = raw.get("pbp", pd.DataFrame())
    weekly = raw.get("weekly", pd.DataFrame())
    ngs_pass = raw.get("ngs_passing", pd.DataFrame())
    ngs_recv = raw.get("ngs_receiving", pd.DataFrame())
    ngs_rush = raw.get("ngs_rushing", pd.DataFrame())

    if pbp.empty and weekly.empty:
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for season in config.SEASONS:
        qb = _compute_qb_metrics(pbp, ngs_pass, weekly, season)
        recv = _compute_recv_metrics(pbp, weekly, ngs_recv, season)
        rb = _compute_rb_metrics(pbp, weekly, ngs_rush, season)
        for part in (qb, recv, rb):
            if not part.empty:
                frames.append(part)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df = df[df["position"].isin(config.POSITIONS)]
    df = df[df.apply(is_qualified, axis=1)]
    return _apply_volume_metric_columns(_attach_derived_metric_values(df.reset_index(drop=True)))


def _attach_derived_metric_values(df: pd.DataFrame) -> pd.DataFrame:
    """Season values for v12 derived metrics (scrimmage yards, total TDs, dropbacks)."""
    if df.empty:
        return df
    out = df.copy()
    rb_mask = out["position"] == "RB"
    if rb_mask.any():
        rush_yds = pd.to_numeric(out.loc[rb_mask, "rushing_yards"], errors="coerce").fillna(0)
        rec_yds = pd.to_numeric(out.loc[rb_mask, "receiving_yards"], errors="coerce").fillna(0)
        out.loc[rb_mask, "rb_scrimmage_yards_value"] = rush_yds + rec_yds
        rush_td = pd.to_numeric(out.loc[rb_mask, "rushing_tds"], errors="coerce").fillna(0)
        rec_td = pd.to_numeric(out.loc[rb_mask, "receiving_tds"], errors="coerce").fillna(0)
        out.loc[rb_mask, "rb_total_tds_value"] = rush_td + rec_td
    qb_mask = out["position"] == "QB"
    if qb_mask.any() and "dropbacks" in out.columns:
        out.loc[qb_mask, "vol_dropbacks_value"] = pd.to_numeric(
            out.loc[qb_mask, "dropbacks"], errors="coerce"
        )
    return out


def _apply_volume_metric_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map raw counting-stat columns onto vol_* metric value fields for z-scores and UI."""
    if df.empty:
        return df
    out = df.copy()
    for pos in config.POSITIONS:
        mask = out["position"] == pos
        if not mask.any():
            continue
        for mid, meta in config.METRIC_DEFINITIONS.get(pos, {}).items():
            src = meta.get("source_col")
            if not src or src not in out.columns:
                continue
            out.loc[mask, f"{mid}_value"] = out.loc[mask, src]
    return out


def _oriented_values_for_metric(
    out: pd.DataFrame,
    value_col: str,
    metric_id: str,
) -> pd.Series:
    """Player values on the oriented scale used for z-scores."""
    oriented = pd.Series(np.nan, index=out.index, dtype=float)
    for position in config.POSITIONS:
        if not config.metric_applies_to_position(metric_id, position):
            continue
        mask = out["position"] == position
        vals = pd.to_numeric(out.loc[mask, value_col], errors="coerce")
        if config.metric_pushes_toward_lower_z(metric_id, position):
            oriented.loc[mask] = (-vals).to_numpy()
        else:
            oriented.loc[mask] = vals.to_numpy()
    return oriented


def _display_expected_series(
    oriented_mean: pd.Series,
    metric_id: str,
    positions: pd.Series,
) -> pd.Series:
    """Vectorized raw-scale baseline for UI (inverse of orientation flip)."""
    exp = oriented_mean.astype(float).copy()
    for position in config.POSITIONS:
        if not config.metric_applies_to_position(metric_id, position):
            continue
        mask = positions == position
        if config.metric_pushes_toward_lower_z(metric_id, position):
            exp.loc[mask] = -exp.loc[mask]
    return exp


def add_z_scores(
    df: pd.DataFrame,
    df_rosters: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Add per-metric expected and z-score columns.

    Baseline: prior-season qualified players in position peak age (oriented scale).
    Direction-aware metrics are flipped so positive z always favors better play.
    """
    if df.empty:
        return df

    out = _attach_player_ages(df, df_rosters)
    out["age_curve_value"] = out.apply(
        lambda r: _age_curve_value(r.get("player_age"), r.get("position", "")),
        axis=1,
    )
    value_cols = [c for c in out.columns if c.endswith("_value")]

    z_columns: dict[str, pd.Series] = {}
    expected_columns: dict[str, pd.Series] = {}

    for col in value_cols:
        metric_id = col.replace("_value", "")
        z_col = f"{metric_id}_z"
        exp_col = f"{metric_id}_expected"
        stats = _peak_age_position_stats(out, col, metric_id)
        if stats.empty:
            z_columns[z_col] = pd.Series(0.0, index=out.index)
            expected_columns[exp_col] = pd.Series(np.nan, index=out.index)
            continue

        stats = stats.rename(columns={"oriented_mean": "_om", "oriented_std": "_os"})
        baseline = out[["season", "position"]].merge(
            stats, on=["season", "position"], how="left"
        )
        oriented_player = _oriented_values_for_metric(out, col, metric_id)
        om = baseline["_om"]
        os_std = baseline["_os"]
        z_columns[z_col] = pd.Series(
            np.where(
                oriented_player.isna() | om.isna() | os_std.isna() | (os_std == 0),
                0.0,
                (oriented_player - om) / os_std,
            ),
            index=out.index,
        )
        expected_columns[exp_col] = _display_expected_series(
            om, metric_id, out["position"]
        )

    if not z_columns:
        return out

    score_block = pd.DataFrame({**z_columns, **expected_columns})
    return pd.concat([out, score_block], axis=1)


def _percentile_zero_to_one(series: pd.Series) -> pd.Series:
    """Percentile rank in [0,1], using average rank for ties."""
    s = pd.to_numeric(series, errors="coerce")
    valid = s.notna()
    out = pd.Series(np.nan, index=s.index, dtype=float)
    if valid.sum() == 0:
        return out
    ranks = s[valid].rank(method="average", pct=True)
    out.loc[valid] = ranks.clip(0, 1)
    return out


def _volume_column_for_position(position: str) -> str:
    if position == "QB":
        return "dropbacks"
    if position in RECV_POSITIONS:
        return "targets"
    if position == "RB":
        return "carries"
    return "targets"


def _apply_composite_adjustments(df: pd.DataFrame) -> pd.DataFrame:
    """
    v12: assign player tags from role / efficiency / production z-scores.

    ``composite_z`` / ``composite_z_adjusted`` track production z for sorting.
    Sustainability fields are omitted (replaced by explicit role z).
    """
    if df.empty:
        return df

    out = df.copy()
    if "role_z" not in out.columns:
        out["role_z"] = 0.0
    if "efficiency_z" not in out.columns:
        out["efficiency_z"] = 0.0
    if "production_z" not in out.columns:
        out["production_z"] = out.get("composite_z", 0.0)

    out["composite_z"] = out["production_z"]
    out["composite_z_adjusted"] = out["production_z"]
    return reapply_player_tags(out)


def reapply_player_tags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Recompute player flags from axis z-scores using current config.TAG_* cutoffs.

    Use after changing tag thresholds so the UI updates without a full metrics rebuild.
    """
    if df.empty:
        return df

    out = df.copy()
    if "role_z" not in out.columns:
        out["role_z"] = 0.0
    if "efficiency_z" not in out.columns:
        out["efficiency_z"] = 0.0
    if "production_z" not in out.columns:
        out["production_z"] = out.get("composite_z", 0.0)

    out["_volume_qualified"] = out.apply(is_qualified, axis=1)
    out["flag"] = out.apply(assign_player_tag_from_row, axis=1).apply(config.normalize_player_flag)
    out["refined_flag"] = out["flag"]
    out["regression_flag"] = out["flag"]
    out = out.drop(columns=["_volume_qualified"], errors="ignore")
    return apply_flag_labels(out)


def _leaderboard_rows_from_scored(df_all: pd.DataFrame, season: int) -> pd.DataFrame:
    """Convert scored player-season rows into leaderboard records."""
    current = df_all[df_all["season"] == season].copy()
    if current.empty:
        return build_empty_metrics_df()

    rows: list[dict[str, Any]] = []
    for _, player in current.iterrows():
        position = player["position"]
        metric_ids = list(config.METRIC_DEFINITIONS.get(position, {}).keys())
        z_map = {
            mid: player.get(f"{mid}_z", np.nan)
            for mid in metric_ids
            if f"{mid}_z" in player.index
        }
        axes = compute_axis_scores(
            z_map,
            position,
            age_curve_value=player.get("age_curve_value"),
        )
        composite = axes["production_z"]
        primary_id = _primary_metric_id(position)
        primary_val = player.get(f"{primary_id}_value", np.nan)
        expected = player.get(f"{primary_id}_expected", np.nan)

        row = {
            "player_id": player["player_id"],
            "player_name": player.get("player_name", ""),
            "position": position,
            "team": player.get("team", ""),
            "season": int(player["season"]),
            "week_end": int(player.get("week_end", 0)),
            "dropbacks": player.get("dropbacks"),
            "targets": player.get("targets"),
            "carries": player.get("carries"),
            "primary_metric": primary_id,
            "primary_metric_name": config.METRIC_DEFINITIONS[position][primary_id]["name"],
            "primary_value": primary_val,
            "primary_expected": expected,
            "composite_z": composite,
            "composite_z_adjusted": composite,
            "role_z": axes["role_z"],
            "efficiency_z_raw": axes["efficiency_z_raw"],
            "efficiency_age_z_adjustment": axes["efficiency_age_z_adjustment"],
            "efficiency_z": axes["efficiency_z"],
            "production_z": axes["production_z"],
            "flag": "neutral",
            "regression_flag": "neutral",
            "refined_flag": "neutral",
            "scoring_version": config.METRICS_SCORING_VERSION,
        }
        for col in config.VOLUME_STAT_FIELDS:
            if col in player.index:
                row[col] = player.get(col)
        for mid in metric_ids:
            val_col = f"{mid}_value"
            row[val_col] = player.get(val_col, np.nan)
            row[f"{mid}_z"] = player.get(f"{mid}_z", np.nan)
            row[f"{mid}_expected"] = player.get(f"{mid}_expected", np.nan)
        rows.append(row)

    return _apply_composite_adjustments(pd.DataFrame(rows))


def metric_view_options(_positions: list[str] | str | None = None) -> list[dict[str, str]]:
    """Dropdown options for leaderboard focus score (v12 axes only)."""
    return [
        {"label": label, "value": value}
        for value, label in config.LEADERBOARD_SCORE_VIEW_OPTIONS
    ]


def apply_leaderboard_metric_view(df: pd.DataFrame, metric_view: str | None) -> pd.DataFrame:
    """
    Sort and annotate rows for the selected v12 score view (production / role / efficiency z).
    """
    if df.empty:
        return df

    view = config.normalize_score_view(metric_view)
    z_col = config.score_view_z_column(view)
    out = df.copy()
    out["focus_metric"] = view
    z_series = pd.to_numeric(out.get(z_col), errors="coerce")
    out["focus_percentile"] = position_cohort_percentile(z_series, out["position"])
    if view == config.METRIC_VIEW_PRODUCTION:
        out["composite_percentile"] = out["focus_percentile"]
    return apply_flag_labels(out).sort_values(z_col, ascending=False, na_position="last")


def build_df_metrics(
    raw: dict[str, pd.DataFrame],
    season: int | None = None,
) -> pd.DataFrame:
    """Build leaderboard DataFrame with z-scores and flags for a given season."""
    season = season or config.ANALYSIS_SEASON
    df_all = add_z_scores(
        compute_all_season_metrics(raw),
        df_rosters=raw.get("rosters"),
    )
    if df_all.empty:
        return build_empty_metrics_df()

    if df_all[df_all["season"] == season].empty:
        logger.warning("No qualified players for season %s", season)
        return build_empty_metrics_df()

    return _leaderboard_rows_from_scored(df_all, season)


def _player_bio_map(df_rosters: pd.DataFrame, season: int) -> pd.DataFrame:
    """Player id → age and NFL experience from seasonal rosters."""
    empty = pd.DataFrame(columns=["player_id", "player_age", "years_exp"])
    if df_rosters.empty:
        return empty

    roster = df_rosters.copy()
    if "season" in roster.columns:
        roster = roster[roster["season"] == season]

    id_col = "gsis_id" if "gsis_id" in roster.columns else "player_id"
    if id_col not in roster.columns:
        return empty

    bio = roster.drop_duplicates(id_col).copy()
    bio = bio.rename(columns={id_col: "player_id"})
    out = bio[["player_id"]].copy()

    if "years_exp" in bio.columns:
        out["years_exp"] = pd.to_numeric(bio["years_exp"], errors="coerce")
    else:
        out["years_exp"] = np.nan

    if "age" in bio.columns:
        out["player_age"] = pd.to_numeric(bio["age"], errors="coerce")
    elif "birth_date" in bio.columns:
        ref = pd.Timestamp(season, 9, 1)
        birth = pd.to_datetime(bio["birth_date"], errors="coerce")
        out["player_age"] = ((ref - birth).dt.days / 365.25).round(1)
    else:
        out["player_age"] = np.nan

    return out


def enrich_leaderboard_for_display(
    df: pd.DataFrame,
    df_rosters: pd.DataFrame | None = None,
    season: int | None = None,
) -> pd.DataFrame:
    """Attach roster bio fields and percentile ranks for leaderboard tables."""
    if df.empty:
        return df

    season = season or config.ANALYSIS_SEASON
    out = df.copy()

    if df_rosters is not None and not df_rosters.empty:
        bio = _player_bio_map(df_rosters, season)
        out = out.drop(columns=["player_age", "years_exp"], errors="ignore")
        out = out.merge(bio, on="player_id", how="left")

    prod_z = pd.to_numeric(
        out.get("production_z", out.get("composite_z_adjusted")),
        errors="coerce",
    )
    out["composite_percentile"] = position_cohort_percentile(prod_z, out["position"])
    if "focus_percentile" not in out.columns:
        out["focus_percentile"] = out["composite_percentile"]
    return out


def _roster_team_map(df_rosters: pd.DataFrame, season: int) -> pd.DataFrame:
    """Player id → team/position from seasonal rosters."""
    if df_rosters.empty:
        return pd.DataFrame(columns=["player_id", "roster_team", "roster_position"])

    roster = df_rosters.copy()
    if "season" in roster.columns:
        roster = roster[roster["season"] == season]

    id_col = "gsis_id" if "gsis_id" in roster.columns else "player_id"
    team_col = "team" if "team" in roster.columns else "recent_team"
    if id_col not in roster.columns or team_col not in roster.columns:
        return pd.DataFrame(columns=["player_id", "roster_team", "roster_position"])

    out = roster.drop_duplicates(id_col)[[id_col, team_col]].copy()
    out.columns = ["player_id", "roster_team"]
    if "position" in roster.columns:
        pos = roster.drop_duplicates(id_col).set_index(id_col)["position"]
        out["roster_position"] = out["player_id"].map(pos)
    return out


def build_outlook_2026_df(
    df_metrics: pd.DataFrame,
    df_rosters: pd.DataFrame,
) -> pd.DataFrame:
    """
    2026 outlook: all regression candidates (positive and negative) from ANALYSIS_SEASON.
    Projected team from ROSTER_SEASON_FOR_OUTLOOK (2025) rosters. Rookies not modeled.
    """
    empty_cols = [
        "player_id",
        "player_name",
        "position",
        "projected_team",
        "composite_z",
        "primary_metric_name",
        "primary_value",
        "primary_expected",
        "flag",
        "flag_label",
        "outlook_type",
        "outlook_season",
        "analysis_season",
    ]
    if df_metrics is None or df_metrics.empty:
        return pd.DataFrame(columns=empty_cols)

    outlook = df_metrics[
        (df_metrics["season"] == config.ANALYSIS_SEASON)
        & (df_metrics["flag"].isin(config.OUTLOOK_REGRESSION_FLAGS))
    ].copy()
    if outlook.empty:
        return pd.DataFrame(columns=empty_cols)

    roster_map = _roster_team_map(df_rosters, config.ROSTER_SEASON_FOR_OUTLOOK)
    if not roster_map.empty:
        outlook = outlook.merge(roster_map, on="player_id", how="left")
        outlook["projected_team"] = outlook["roster_team"].fillna(outlook["team"])
    else:
        outlook["projected_team"] = outlook["team"]

    outlook["outlook_season"] = config.OUTLOOK_SEASON
    outlook["analysis_season"] = config.ANALYSIS_SEASON
    outlook = apply_flag_labels(outlook)
    outlook["outlook_type"] = outlook["flag"].map(
        {
            "star": "Star (sustainable production)",
            "breakout": "Breakout (role upside)",
            "positive_outlook": "Positive outlook",
            "regress_negative": "Fade (negative regression)",
        }
    ).fillna(outlook["flag_label"])
    if "composite_z_adjusted" in outlook.columns:
        outlook["composite_z"] = outlook["composite_z_adjusted"]
    outlook["composite_z_abs"] = outlook["composite_z"].abs()

    return outlook.sort_values("composite_z_abs", ascending=False).reset_index(drop=True)


def build_team_summary_df(df_metrics: pd.DataFrame) -> pd.DataFrame:
    """Net regression score per team (sum of player composite z-scores)."""
    if df_metrics is None or df_metrics.empty or "team" not in df_metrics.columns:
        return pd.DataFrame(columns=["team", "net_regression_score", "player_count"])

    summary = (
        df_metrics.groupby("team", as_index=False)
        .agg(
            net_regression_score=("composite_z_adjusted", "sum"),
            player_count=("player_id", "count"),
        )
        .sort_values("net_regression_score", ascending=False)
    )
    return summary.reset_index(drop=True)


def build_empty_metrics_df() -> pd.DataFrame:
    """Return an empty metrics DataFrame with expected columns."""
    cols = [
        "player_id",
        "player_name",
        "position",
        "team",
        "season",
        "week_end",
        "dropbacks",
        "targets",
        "carries",
        "primary_metric",
        "primary_metric_name",
        "primary_value",
        "primary_expected",
        "composite_z",
        "composite_z_adjusted",
        "role_z",
        "efficiency_z",
        "production_z",
        "flag",
        "regression_flag",
        "refined_flag",
        *config.VOLUME_STAT_FIELDS,
    ]
    for mid in ALL_METRIC_IDS:
        cols.extend([f"{mid}_value", f"{mid}_z"])
    return pd.DataFrame(columns=cols)


def get_player_weekly_volume_series(
    raw: dict[str, pd.DataFrame],
    player_id: str,
    position: str,
    season: int | None = None,
) -> tuple[list[int], dict[str, list[float]]]:
    """
    Per-week box-score totals for the player detail chart.

    Returns weeks played and a dict of series label → weekly values (not cumulative).
    """
    season = season or config.ANALYSIS_SEASON
    series_defs = config.PLAYER_WEEKLY_CHART_SERIES.get(position, [])
    if not series_defs:
        return [], {}

    weekly = raw.get("weekly", pd.DataFrame())
    if weekly.empty or not player_id:
        return [], {}

    wk = weekly[(weekly["player_id"] == player_id) & (weekly["season"] == season)].copy()
    if wk.empty:
        return [], {}

    stat_cols = [col for col, _ in series_defs if col in wk.columns]
    if not stat_cols:
        return [], {}

    by_week = (
        wk.groupby("week", as_index=False)[stat_cols]
        .sum(min_count=1)
        .sort_values("week")
    )
    weeks = by_week["week"].astype(int).tolist()
    series: dict[str, list[float]] = {}
    for col, label in series_defs:
        if col not in by_week.columns:
            continue
        values = by_week[col].fillna(0).round(1 if col in config.PLAYER_WEEKLY_YARD_STATS else 0)
        series[label] = values.tolist()
    return weeks, series


def get_player_weekly_series(
    raw: dict[str, pd.DataFrame],
    player_id: str,
    metric_id: str,
    position: str,
) -> tuple[list[int], list[float], float | None]:
    """Return weeks, cumulative actual series, and baseline expected for trend chart."""
    weekly = raw.get("weekly", pd.DataFrame())
    pbp = raw.get("pbp", pd.DataFrame())
    expected = np.nan
    season = config.ANALYSIS_SEASON

    metrics_df = compute_all_season_metrics(raw)
    baseline_season = config.z_score_baseline_season(season)
    value_col = f"{metric_id}_value"
    if not metrics_df.empty and value_col in metrics_df.columns:
        pop = metrics_df[
            (metrics_df["season"] == baseline_season)
            & (metrics_df["position"] == position)
        ][value_col].dropna()
        if not pop.empty:
            expected = float(pop.mean())

    meta = config.METRIC_DEFINITIONS.get(position, {}).get(metric_id, {})
    source_col = meta.get("source_col") if meta else None
    if source_col and not weekly.empty:
        wk = weekly[(weekly["player_id"] == player_id) & (weekly["season"] == season)].copy()
        if position:
            wk = wk[wk["position"] == position]
        if not wk.empty and source_col in wk.columns:
            by_week = wk.groupby("week", as_index=False)[source_col].sum().sort_values("week")
            cum = by_week[source_col].cumsum()
            return by_week["week"].astype(int).tolist(), cum.round(2).tolist(), expected

    baseline_df = metrics_df

    season = config.ANALYSIS_SEASON
    if metric_id == "recv_target_share" and not weekly.empty:
        wk = weekly[
            (weekly["player_id"] == player_id)
            & (weekly["season"] == season)
            & (weekly["position"].isin(RECV_POSITIONS))
        ].sort_values("week")
        if wk.empty:
            return [], [], expected
        cum = wk["target_share"].expanding().mean()
        return wk["week"].astype(int).tolist(), cum.round(4).tolist(), expected

    if metric_id == "recv_ypt" and not weekly.empty:
        wk = weekly[
            (weekly["player_id"] == player_id)
            & (weekly["season"] == season)
            & (weekly["position"].isin(RECV_POSITIONS))
        ].sort_values("week")
        if wk.empty:
            return [], [], expected
        cum_yds = wk["receiving_yards"].fillna(0).cumsum()
        cum_tgt = wk["targets"].fillna(0).cumsum().replace(0, np.nan)
        cum = cum_yds / cum_tgt
        return wk["week"].astype(int).tolist(), cum.round(2).tolist(), expected

    if metric_id == "age_curve":
        metrics_df = compute_all_season_metrics(raw)
        metrics_df = _attach_player_ages(metrics_df, raw.get("rosters"))
        if not metrics_df.empty:
            row = metrics_df[
                (metrics_df["player_id"] == player_id)
                & (metrics_df["season"] == season)
                & (metrics_df["position"] == position)
            ]
            if not row.empty:
                v = _age_curve_value(row.iloc[0].get("player_age"), position)
                if pd.notna(v):
                    week_end = int(row.iloc[0].get("week_end", 1))
                    weeks = list(range(1, week_end + 1)) if week_end >= 1 else [1]
                    return weeks, [round(v, 1)] * len(weeks), expected

    if metric_id == "rb_target_share" and not weekly.empty:
        wk = weekly[
            (weekly["player_id"] == player_id)
            & (weekly["season"] == season)
            & (weekly["position"] == "RB")
        ].sort_values("week")
        if wk.empty:
            return [], [], expected
        cum = wk["target_share"].expanding().mean()
        return wk["week"].astype(int).tolist(), cum.round(4).tolist(), expected

    if metric_id == "qb_cpoe" and not pbp.empty:
        passes = pbp[
            (pbp["passer_player_id"] == player_id)
            & (pbp["season"] == season)
            & (pbp["pass_attempt"] == 1)
            & pbp["cp"].notna()
        ].copy()
        if passes.empty:
            return [], [], expected
        passes["cpoe"] = passes["complete_pass"] - passes["cp"]
        weekly_cpoe = passes.groupby("week")["cpoe"].mean().reset_index().sort_values("week")
        cum = weekly_cpoe["cpoe"].expanding().mean()
        return (
            weekly_cpoe["week"].astype(int).tolist(),
            cum.round(4).tolist(),
            expected,
        )

    if metric_id == "qb_completion_percentage_above_expectation" and not raw.get("ngs_passing", pd.DataFrame()).empty:
        ngs = raw.get("ngs_passing", pd.DataFrame())
        pr = ngs[
            (ngs["player_gsis_id"] == player_id)
            & (ngs["season"] == season)
            & (ngs["week"] >= 1)
        ].sort_values("week")
        if not pr.empty and "completion_percentage_above_expectation" in pr.columns:
            att = pr.get("attempts", pd.Series([np.nan] * len(pr)))
            w = att.clip(lower=1)
            cum_num = (pr["completion_percentage_above_expectation"] * w).cumsum()
            cum_den = w.cumsum().replace(0, np.nan)
            cum = cum_num / cum_den
            return pr["week"].astype(int).tolist(), cum.round(4).tolist(), expected

    if metric_id == "rb_ryoe":
        ngs = raw.get("ngs_rushing", pd.DataFrame())
        if ngs.empty:
            return [], [], expected
        pr = ngs[
            (ngs["player_gsis_id"] == player_id) & (ngs["season"] == season) & (ngs["week"] >= 1)
        ].sort_values("week")
        if pr.empty or "rush_yards_over_expected" not in pr.columns:
            return [], [], expected
        cum = pr["rush_yards_over_expected"].cumsum()
        return pr["week"].astype(int).tolist(), cum.round(1).tolist(), expected

    if metric_id in ("rb_avg_time_to_los", "rb_efficiency") and not raw.get("ngs_rushing", pd.DataFrame()).empty:
        ngs = raw.get("ngs_rushing", pd.DataFrame())
        pr = ngs[
            (ngs["player_gsis_id"] == player_id)
            & (ngs["season"] == season)
            & (ngs["week"] >= 1)
        ].sort_values("week")
        if pr.empty:
            return [], [], expected
        src_col = "avg_time_to_los" if metric_id == "rb_avg_time_to_los" else "efficiency"
        if src_col not in pr.columns:
            return [], [], expected
        att = pr.get("rush_attempts", pd.Series([np.nan] * len(pr)))
        w = att.clip(lower=1)
        cum_num = (pr[src_col] * w).cumsum()
        cum_den = w.cumsum().replace(0, np.nan)
        cum = cum_num / cum_den
        return pr["week"].astype(int).tolist(), cum.round(3).tolist(), expected

    if metric_id == "recv_separation":
        ngs = raw.get("ngs_receiving", pd.DataFrame())
        if not ngs.empty and "avg_separation" in ngs.columns:
            pr = ngs[
                (ngs["player_gsis_id"] == player_id) & (ngs["season"] == season) & (ngs["week"] >= 1)
            ].sort_values("week")
            if not pr.empty:
                return (
                    pr["week"].astype(int).tolist(),
                    pr["avg_separation"].round(2).tolist(),
                    expected,
                )

    if metric_id == "recv_yac_oe" and not pbp.empty:
        recv = pbp[
            (pbp["receiver_player_id"] == player_id)
            & (pbp["season"] == season)
            & (pbp["pass_attempt"] == 1)
            & pbp["xyac_mean_yardage"].notna()
        ].copy()
        if not recv.empty:
            recv["yac_oe"] = recv["yards_after_catch"] - recv["xyac_mean_yardage"]
            by_week = recv.groupby("week")["yac_oe"].mean().reset_index().sort_values("week")
            cum = by_week["yac_oe"].expanding().mean()
            return by_week["week"].astype(int).tolist(), cum.round(3).tolist(), expected

    if metric_id == "recv_catch_rate_oe" and not pbp.empty:
        tgt = pbp[
            (pbp["receiver_player_id"] == player_id)
            & (pbp["season"] == season)
            & (pbp["pass_attempt"] == 1)
            & pbp["cp"].notna()
        ].copy()
        if not tgt.empty:
            by_week = (
                tgt.groupby("week")
                .apply(
                    lambda g: (g["complete_pass"].sum() / len(g)) - g["cp"].mean(),
                    include_groups=False,
                )
                .reset_index(name="catch_oe")
                .sort_values("week")
            )
            cum = by_week["catch_oe"].expanding().mean()
            return by_week["week"].astype(int).tolist(), cum.round(3).tolist(), expected

    val_col = f"{metric_id}_value"
    if not baseline_df.empty:
        player_row = baseline_df[
            (baseline_df["player_id"] == player_id) & (baseline_df["season"] == season)
        ]
        if not player_row.empty and val_col in player_row.columns:
            v = float(player_row.iloc[0][val_col])
            if not np.isnan(v):
                return [int(player_row.iloc[0].get("week_end", 1))], [round(v, 4)], expected

    return [], [], expected


def build_player_insight(row: pd.Series) -> str:
    """Generate short insight text for player detail panel."""
    name = row.get("player_name", "Player")
    flag = config.FLAG_LABELS.get(row.get("flag", "neutral"), "Neutral")
    focus = config.normalize_score_view(row.get("focus_metric"))
    z_col = config.score_view_z_column(focus)
    z = row.get(z_col, row.get("composite_z", 0.0))
    pct = row.get("focus_percentile", row.get("composite_percentile", np.nan))
    if pd.isna(pct):
        pct = z_to_percentile(float(z) if pd.notna(z) else 0.0)

    score_label = config.score_view_label(focus)
    if focus != config.METRIC_VIEW_PRODUCTION:
        pos = row.get("position", "")
        peak_lo, peak_hi = config.position_peak_age_range(pos) if pos else (0, 0)
        return (
            f"{name} ranks at the {pct:.1f}th percentile on {score_label} "
            f"({float(z):+.2f} vs. {pos} peak-age {peak_lo}–{peak_hi} baseline). {flag}."
        )

    age = row.get("player_age", np.nan)
    exp_yrs = row.get("years_exp", np.nan)
    pos = row.get("position", "")
    peak_lo, peak_hi = config.position_peak_age_range(pos) if pos else (0, 0)
    age_s = f"{age:.0f}" if pd.notna(age) else "N/A"
    exp_yrs_s = f"{exp_yrs:.0f}" if pd.notna(exp_yrs) else "N/A"
    return (
        f"{name} (age {age_s}, {exp_yrs_s} yrs experience) ranks at the {pct:.1f}th percentile "
        f"overall vs. {pos} peak-age ({peak_lo}–{peak_hi}) baseline. {flag}."
    )
