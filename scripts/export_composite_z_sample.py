"""Export a random sample of players with composite z-score math breakdown."""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from metrics.calculator import (
    add_z_scores,
    compute_all_season_metrics,
    compute_composite_z,
    get_metric_weight,
)
from metrics.loader import load_all_data

DEFAULT_OUTPUT = ROOT / "composite_z_sample_breakdown.txt"


def _fmt_num(val: float | None, width: int = 8, decimals: int = 3) -> str:
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return " " * (width - 3) + "N/A"
    return f"{float(val):>{width}.{decimals}f}"


def composite_breakdown_lines(row: pd.Series) -> list[str]:
    """Build text lines showing weighted composite z math for one player."""
    position = row["position"]
    metric_ids = list(config.METRIC_DEFINITIONS.get(position, {}).keys())
    lines: list[str] = []

    age = row.get("player_age", np.nan)
    age_s = f"{age:.0f}" if pd.notna(age) else "N/A"
    lines.append("=" * 88)
    lines.append(
        f"Player: {row.get('player_name', '')} | {position} | {row.get('team', '')} | "
        f"Season {int(row['season'])} | Age {age_s}"
    )
    lines.append("=" * 88)

    terms: list[dict] = []
    for mid in metric_ids:
        if not config.metric_in_composite(mid, position):
            continue
        z = row.get(f"{mid}_z", np.nan)
        if pd.isna(z):
            continue
        weight = get_metric_weight(mid, position)
        meta = config.METRIC_DEFINITIONS[position][mid]
        terms.append(
            {
                "metric_id": mid,
                "name": meta.get("name", mid),
                "category": meta.get("weight_category", "default"),
                "value": row.get(f"{mid}_value", np.nan),
                "expected": row.get(f"{mid}_expected", np.nan),
                "z": float(z),
                "weight": weight,
                "weighted": float(z) * weight,
            }
        )

    weighted_sum = sum(t["weighted"] for t in terms)
    weight_total = sum(t["weight"] for t in terms)
    composite = weighted_sum / weight_total if weight_total else 0.0
    composite_check = compute_composite_z(
        {t["metric_id"]: t["z"] for t in terms},
        position,
    )

    lines.append(
        f"Composite Z: {composite:+.4f}  "
        f"(recomputed check: {composite_check:+.4f})"
    )
    lines.append("")
    lines.append("Formula:  composite_z = sum(z_i * weight_i) / sum(weight_i)")
    lines.append("")
    header = (
        f"{'Metric':<28} {'Value':>8} {'Expected':>9} {'Z':>8} "
        f"{'WtCat':<18} {'Weight':>7} {'Z*W':>9}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for t in sorted(terms, key=lambda x: -abs(x["weighted"])):
        lines.append(
            f"{t['name']:<28} "
            f"{_fmt_num(t['value'], 8)} "
            f"{_fmt_num(t['expected'], 9)} "
            f"{t['z']:+8.3f} "
            f"{t['category']:<18} "
            f"{t['weight']:7.2f} "
            f"{t['weighted']:+9.4f}"
        )

    lines.append("-" * len(header))
    lines.append(
        f"{'SUM (z * weight)':<28} {'':>8} {'':>9} {'':>8} {'':<18} {'':>7} {weighted_sum:+9.4f}"
    )
    lines.append(
        f"{'SUM (weights)':<28} {'':>8} {'':>9} {'':>8} {'':<18} {'':>7} {weight_total:9.4f}"
    )
    lines.append("")
    lines.append(
        f"COMPOSITE = {weighted_sum:.4f} / {weight_total:.4f} = {composite:+.4f}"
    )
    lines.append("")
    return lines


def export_sample(
    output_path: Path,
    n: int = 50,
    season: int | None = None,
    seed: int = 42,
) -> Path:
    season = season or config.ANALYSIS_SEASON
    raw = load_all_data()
    df = add_z_scores(compute_all_season_metrics(raw), raw.get("rosters"))
    pool = df[df["season"] == season].copy()
    if pool.empty:
        raise ValueError(f"No qualified player-seasons for season {season}")

    rng = random.Random(seed)
    n = min(n, len(pool))
    sample_idx = rng.sample(list(pool.index), n)
    sample = pool.loc[sample_idx].sort_values(["position", "player_name"])

    lines: list[str] = [
        "NFL Regression Dashboard — Composite Z-Score Breakdown (Random Sample)",
        f"Scoring version: {config.METRICS_SCORING_VERSION}",
        f"Analysis season: {season}",
        f"Regression flag threshold: |composite_z| >= {config.REGRESSION_Z_THRESHOLD}",
        f"Sample size: {n} (seed={seed})",
        "",
        "Per-metric Z: (oriented_value - baseline_mean) / baseline_std",
        "  Performance metrics: baseline = prior-season peak-age cohort at position.",
        "  Age curve: baseline = prior-season full qualified pool; value = years outside",
        "    productive window (negative=young, 0=in window, positive=old).",
        "",
        "Category weights (METRIC_WEIGHTS / age by position):",
        f"  target_share={config.METRIC_WEIGHTS['target_share']}, "
        f"yards_per_target={config.METRIC_WEIGHTS['yards_per_target']}, "
        f"process={config.METRIC_WEIGHTS['process']}, "
        f"td_rate={config.METRIC_WEIGHTS['td_rate']}, "
        f"default={config.METRIC_WEIGHTS['default']}",
        f"  age_curve: RB={config.AGE_CURVE_WEIGHT_BY_POSITION['RB']}, "
        f"WR/TE={config.AGE_CURVE_WEIGHT_BY_POSITION['WR']}, "
        f"QB={config.AGE_CURVE_WEIGHT_BY_POSITION['QB']}",
        "",
    ]

    for _, row in sample.iterrows():
        lines.extend(composite_breakdown_lines(row))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-n", type=int, default=50, help="Sample size")
    parser.add_argument("-o", type=Path, default=DEFAULT_OUTPUT, help="Output file path")
    parser.add_argument("--season", type=int, default=None, help="Season (default: ANALYSIS_SEASON)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()
    path = export_sample(args.o, n=args.n, season=args.season, seed=args.seed)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
