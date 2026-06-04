# project.md — NFL NGS Regression Dashboard

Cursor: read this file at the start of every session. It is the source of truth for
conventions, constraints, and decisions already made.

---

## Stack

- **UI**: Dash + dash-bootstrap-components (DARKLY theme)
- **Data**: nfl_data_py, pandas, numpy, scipy
- **Charts**: plotly.express and plotly.graph_objects (no other charting libraries)
- **Cache**: Parquet files in /data via pandas read/write_parquet
- **Python**: 3.11+ (3.13 supported; requires `numpy>=2.0` — see `requirements.txt`)
- **Setup**: `python -m venv .venv` then `.\install.ps1` (do not `pip install nfl-data-py` alone — its PyPI pins conflict with Python 3.13 wheels)
- **No database** — everything in-memory or Parquet

---

## File Conventions

- One component per file in /components/
- All Dash callbacks go in callbacks.py (or split as callbacks_leaderboard.py etc. if file exceeds 300 lines)
- Config values (thresholds, metric definitions, column name maps) go in config.py — never hardcoded inline
- All data fetching and cache logic goes in metrics/loader.py
- All z-score and regression flag logic goes in metrics/calculator.py
- Assets (CSS overrides) in /assets/custom.css — DBC DARKLY handles most styling

---

## Naming Conventions

- DataFrames: `df_` prefix (e.g. `df_players`, `df_metrics`)
- Dash component IDs: kebab-case strings (e.g. `"leaderboard-table"`, `"position-filter"`)
- Metric IDs: snake_case with position prefix (e.g. `qb_cpoe`, `recv_target_share`, `rb_ryoe`)
- Parquet files: `{source}_{year}.parquet` (e.g. `weekly_2025.parquet`)
- Functions: verb_noun pattern (e.g. `compute_z_scores`, `load_pbp_data`, `flag_regression`)

---

## nfl_data_py Column Reference

Key columns used across the project. Do not rename or alias these — use as-is from the library.

**Play-by-play (`import_pbp_data`)**
```
passer_player_id, receiver_player_id, rusher_player_id
posteam, season, week
pass_attempt, complete_pass, incomplete_pass
air_yards, yards_after_catch, yards_gained
pass_touchdown, rush_touchdown, receiving_touchdown
sack, was_pressure
cp                  # completion probability (model)
xyac_mean_yardage   # expected yards after catch
red_zone            # 1 if play inside opponent 20
```

**Weekly stats (`import_weekly_data`)**
```
player_id, player_name, position, recent_team
season, week
completions, attempts, passing_yards, passing_tds, interceptions
carries, rushing_yards, rushing_tds
receptions, targets, receiving_yards, receiving_tds
target_share, air_yards_share
wopr                # weighted opportunity rating
racr                # receiver air conversion ratio
```

**NGS passing (`import_ngs_data(stat_type='passing')`)**
```
player_gsis_id, player_display_name, team_abbr
season, week
avg_time_to_throw, avg_completed_air_yards, avg_intended_air_yards
completion_percentage_above_expectation   # CPOE
passer_rating, attempts
```

**NGS receiving (`import_ngs_data(stat_type='receiving')`)**
```
player_gsis_id, player_display_name, team_abbr
season, week
avg_separation, avg_intended_air_yards, avg_yac_above_expectation
catch_percentage, targets, receptions
```

**NGS rushing (`import_ngs_data(stat_type='rushing')`)**
```
player_gsis_id, player_display_name, team_abbr
season, week
rush_yards_over_expected, rush_yards_over_expected_per_att
efficiency, percent_attempts_gte_eight_defenders
rushes
```

---

## Season Scope

- **Data seasons**: 2023, 2024, 2025 (`SEASONS`)
- **Analysis season**: 2025 (`ANALYSIS_SEASON`) — full-season metrics and leaderboard
- **Outlook season**: 2026 (`OUTLOOK_SEASON`) — forward regression outlook (predictive; no 2026 stats yet)
- **Rosters for outlook**: 2025 end-of-season (`ROSTER_SEASON_FOR_OUTLOOK`) — projected team for 2026 view; rookies out of scope
- **Z-score baseline**: 2023–2024 (`BASELINE_SEASONS`) — analysis season excluded from population
- **`CURRENT_SEASON`**: alias for `ANALYSIS_SEASON` (backward compatibility)

---

## Regression Logic (summary — full spec in PRD.md §5)

1. For each metric, compute player's season-to-date value
2. Compute z-score against peak-age cohort from prior season (`z_score_baseline_season`)
3. Build v12 axis scores: `role_z`, `efficiency_z` (age-adjusted), `production_z`
4. Assign player tag via within-position axis percentiles (`New_scoring.txt` / `config.TAG_*_PCT`)
5. `composite_z` / `composite_z_adjusted` = `production_z` (used for leaderboard, team sum, 2026 outlook sort)
6. 2026 outlook includes players whose `flag` is in `OUTLOOK_REGRESSION_FLAGS`
7. Qualification thresholds: QB ≥ 100 dropbacks, WR/TE ≥ 40 targets, RB ≥ 60 carries (`config.py`)

---

## Constraints

- Never re-fetch data if a valid Parquet cache exists (< 7 days old)
- Never use st.* (Streamlit) — this is a Dash app
- Never hardcode player IDs or team abbreviations — always look up from data
- Always handle missing NGS data gracefully (not all players have NGS coverage)
- Dash callback outputs must never raise exceptions — use try/except with fallback UI states
- Keep components pure where possible — data fetching belongs in loader.py, not in component files
- **Metrics iteration**: after editing `metrics/calculator.py` or `config.py` scoring, save the file and click **Refresh metrics** (recomputes from cached raw Parquet). Tag cutoffs (`TAG_*` in config) are re-read on each table update; save `config.py` before refreshing so flags match your thresholds.

---

## Known nfl_data_py Quirks

- `import_pbp_data` is slow (~30s for a full season) — always cache to Parquet
- `import_pbp_data` returns **empty** data if `game_id` is omitted from `columns` — loader always includes it
- Corrupt/empty Parquet caches are auto-deleted and re-fetched on next load
- **`import_weekly_data` has no 2025 file yet** — nflverse publishes through 2024 only.
  For 2025, derive weekly player stats from PBP in `loader.py` (targets, carries, yards,
  `target_share`, etc.). Cache result as `weekly_2025.parquet`. Fall back to
  `import_weekly_data` for 2023–2024.
- Player ID format differs between pbp (`gsis_id`) and weekly data (`player_id`) — join on both
- NGS data uses `player_gsis_id` — map to `gsis_id` when merging with pbp
- Week 0 appears in some datasets (preseason) — always filter `week >= 1`
- Some `cp` values are null on non-pass plays — always filter before aggregating
- Team abbreviations are not always consistent across datasets (e.g. `LV` vs `OAK`) —
  normalize using nfl_data_py's team metadata

---

## Current Status

- [x] Project scaffolded
- [x] Data loader implemented
- [x] Metrics calculator (v12 tagging)
- [x] Leaderboard component
- [x] Player detail view
- [x] Scatter plot
- [x] Callbacks wired
- [x] Styling pass
- [x] 2026 regression outlook — tagged candidates (2025 stats, 2025 rosters)
- [x] Team-level view
- [x] WoW / YoY delta views removed (not in product surface)
