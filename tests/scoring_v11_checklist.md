# Scoring v11 Validation Checklist

- [ ] All four positions (QB, WR, TE, RB) return rows in leaderboard output.
- [ ] `composite_z` (raw) and `composite_z_adjusted` both exist.
- [ ] `regression_flag` (legacy) and `refined_flag` both exist.
- [ ] `flag` mirrors `refined_flag`.
- [ ] `sustainability_score` and `sustainability_label` exist and are populated.
- [ ] Volume scalar fields (`volume_percentile`, `volume_scalar`) exist.
- [ ] Team summary net score uses adjusted composite (`composite_z_adjusted`).
- [ ] `qb_completion_percentage_above_expectation` is excluded from composite.
- [ ] `qb_epa_per_play` is included when `epa` data is present.
- [ ] WR/TE/RB `opportunity_share` is computed and z-scored.
- [ ] WR/TE `vol_air_yards_share` is computed when `air_yards_share` data is present.
- [ ] Volume metrics in scope (`vol_targets`, `vol_carries`) contribute to composite.
