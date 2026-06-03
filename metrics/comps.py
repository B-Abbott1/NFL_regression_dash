"""Historical comparable season matching."""

from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.linalg import norm

import config


def find_similar_seasons(
    df_metrics: pd.DataFrame,
    player_id: str,
    season: int | None = None,
    top_n: int = 5,
) -> pd.DataFrame:
    """
    Find historical player-seasons with similar metric profiles via cosine similarity.

    Returns empty DataFrame until per-metric value columns are populated.
    """
    season = season or config.CURRENT_SEASON
    metric_cols = [c for c in df_metrics.columns if c.endswith("_value")]

    if not metric_cols or df_metrics.empty:
        return pd.DataFrame(
            columns=[
                "player_id",
                "comp_player_id",
                "comp_player_name",
                "comp_season",
                "similarity_score",
            ]
        )

    target = df_metrics[
        (df_metrics["player_id"] == player_id) & (df_metrics["season"] == season)
    ]
    if target.empty:
        return pd.DataFrame(
            columns=[
                "player_id",
                "comp_player_id",
                "comp_player_name",
                "comp_season",
                "similarity_score",
            ]
        )

    baseline = df_metrics[df_metrics["season"].isin(config.BASELINE_SEASONS)].copy()
    target_vec = target[metric_cols].fillna(0).iloc[0].values.astype(float)

    scores: list[dict] = []
    for _, row in baseline.iterrows():
        if row["player_id"] == player_id and row["season"] == season:
            continue
        vec = row[metric_cols].fillna(0).values.astype(float)
        denom = norm(target_vec) * norm(vec)
        similarity = float(np.dot(target_vec, vec) / denom) if denom else 0.0
        scores.append(
            {
                "player_id": player_id,
                "comp_player_id": row["player_id"],
                "comp_player_name": row.get("player_name", ""),
                "comp_season": row["season"],
                "similarity_score": similarity,
            }
        )

    df_comps = pd.DataFrame(scores)
    if df_comps.empty:
        return df_comps

    return df_comps.nlargest(top_n, "similarity_score").reset_index(drop=True)
