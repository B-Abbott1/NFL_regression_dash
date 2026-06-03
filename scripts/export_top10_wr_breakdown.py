from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from metrics.calculator import build_df_metrics, get_metric_weight
from metrics.loader import load_all_data


def main() -> None:
    raw = load_all_data()
    df = build_df_metrics(raw, config.ANALYSIS_SEASON)
    wr = df[df["position"] == "WR"].copy()
    wr = wr.sort_values("receiving_yards", ascending=False).head(10)

    lines: list[str] = []
    lines.append("Top 10 WR by Receiving Yards - v12 Score Breakdown")
    lines.append(f"Season: {config.ANALYSIS_SEASON}  Scoring version: {config.METRICS_SCORING_VERSION}")
    lines.append(f"Tag threshold: +/-{config.TAG_Z_THRESHOLD}")
    lines.append("")

    for _, r in wr.iterrows():
        lines.append("=" * 100)
        lines.append(
            f"{r.get('player_name', '')} | Team {r.get('team', '')} | "
            f"RecYds {float(r.get('receiving_yards', 0) or 0):.0f} | "
            f"Targets {float(r.get('targets', 0) or 0):.0f}"
        )
        lines.append(
            f"role_z={float(r.get('role_z', 0.0)):+.3f} | "
            f"efficiency_z={float(r.get('efficiency_z', 0.0)):+.3f} | "
            f"production_z={float(r.get('production_z', 0.0)):+.3f} | "
            f"flag={r.get('flag', '')}"
        )
        lines.append("")

        mids = (
            config.score_metric_ids("WR", "role")
            + config.score_metric_ids("WR", "efficiency")
            + config.score_metric_ids("WR", "production")
            + config.td_luck_metric_ids("WR")
        )
        rows: list[tuple[str, str, float, float, float]] = []
        for m in mids:
            z = r.get(f"{m}_z", float("nan"))
            if pd.isna(z):
                continue
            w = get_metric_weight(m, "WR")
            rows.append((m, config.METRIC_DEFINITIONS["WR"][m].get("name", m), float(z), float(w), float(z) * float(w)))
        rows = sorted(rows, key=lambda x: abs(x[4]), reverse=True)
        lines.append("Metric contributions (sorted by |z*w|):")
        lines.append("metric_id | name | z | weight | z*w")
        for m, name, z, w, zw in rows:
            lines.append(f"{m} | {name} | {z:+.3f} | {w:.2f} | {zw:+.3f}")
        wsum = sum(x[3] for x in rows)
        zwsum = sum(x[4] for x in rows)
        lines.append(f"SUM(z*w)={zwsum:+.3f}  SUM(w)={wsum:.3f}  Recalc raw={((zwsum / wsum) if wsum else 0):+.3f}")
        lines.append("")

    out = Path("composite_z_sample_breakdown_top10_wr_by_yards.txt")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out.resolve()}")


if __name__ == "__main__":
    main()
