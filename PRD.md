# NFL Next Gen Stats — Player Regression Dashboard
## Product Requirements Document

---

## 1. Project Overview

A web-based analytics dashboard that identifies NFL player regression candidates by comparing
current-season performance metrics against expected baselines derived from NFL Next Gen Stats.
The dashboard surfaces players whose counting stats (TDs, yards, catch rate) are outperforming
or underperforming their underlying process metrics (CPOE, RYOE, separation, target share),
flagging likely positive or negative regression targets.

**Primary user**: Fantasy football analysts, beat reporters, front office staff.
**Core question the dashboard answers**: "Is this player's production real or lucky?"

---

## 2. Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| UI framework | Dash (Plotly) | `dash`, `dash-bootstrap-components` |
| Data fetching | `nfl_data_py` | Primary source for play-by-play and NGS |
| Data processing | `pandas`, `numpy` | All transforms in-memory |
| Caching | Parquet files in `/data` | Refresh weekly; avoid re-fetching |
| Charts | `plotly.express` + `plotly.graph_objects` | Consistent with Dash |
| Styling | `dash-bootstrap-components` (DARKLY theme) | Dark sports-analytics aesthetic |
| Python version | 3.11+ | |

**No external database.** All data lives in Parquet files cached locally and loaded into
Pandas DataFrames at app start.

---

## 3. Data Sources

Use `nfl_data_py` for all data fetching. Key functions:

```python
import nfl_data_py as nfl

# Play-by-play (primary source — most metrics derived here)
nfl.import_pbp_data(years=[2023, 2024, 2025])

# Weekly player stats (aggregated) — 2023–2024 only; see 2025 workaround below
nfl.import_weekly_data(years=[2023, 2024])

# NGS passing stats
nfl.import_ngs_data(stat_type='passing', years=[2023, 2024, 2025])

# NGS receiving stats
nfl.import_ngs_data(stat_type='receiving', years=[2023, 2024, 2025])

# NGS rushing stats
nfl.import_ngs_data(stat_type='rushing', years=[2023, 2024, 2025])

# Rosters / player metadata
nfl.import_seasonal_rosters(years=[2025])
```

**Season scope**:

| Role | Season | Config key |
|------|--------|------------|
| Analysis (leaderboard, flags) | 2025 | `ANALYSIS_SEASON` |
| Forward outlook label | 2026 | `OUTLOOK_SEASON` |
| Projected team (outlook) | 2025 rosters | `ROSTER_SEASON_FOR_OUTLOOK` |
| Z-score baseline population | 2023–2024 | `BASELINE_SEASONS` |

2026 regression outlook uses **2025 stats + flags** (breakout and fade) and **2025 end-of-season rosters** for projected team. No 2026 play-by-play until that season exists. **Rookies are out of scope** for v1 outlook.

**2025 weekly stats workaround**: `import_weekly_data` is not published for 2025 on
nflverse yet. `loader.py` must aggregate weekly player stats from PBP for 2025
(targets, carries, yards, TDs, `target_share`, etc.) and cache as `weekly_2025.parquet`.
Use `import_weekly_data` directly for 2023–2024. Re-check nflverse periodically; swap to
the official file once `player_stats_2025.parquet` appears.

**Cache policy**: Save each fetch to `/data/{source}_{year}.parquet`. Only re-fetch if file
is older than 7 days or does not exist.

---

## 4. Feature List (Priority Order)

### P0 — Core (MVP)

#### 4.1 Regression Leaderboard
A sortable, filterable table showing all qualified players with their regression score.

**Columns:**
| Column | Description |
|---|---|
| Player | Name + headshot thumbnail |
| Position | QB / WR / RB / TE |
| Team | Current team abbreviation |
| Metric | The primary regression metric (e.g. "TD Rate vs. Opportunity") |
| Current | Player's current value (this season) |
| Expected | Model-expected value based on opportunity metrics |
| Z-Score | Standard deviations from expected (positive = overperforming) |
| Flag | Negative regression risk \| Positive regression candidate \| Neutral |
| Season | Analysis season (full regular-season totals) |

**Filters:** Position (multi-select), Flag type, Min volume threshold (slider), Team.
Full regular-season totals only (no week-over-week or year-over-year delta views).

**Acceptance criteria:**
- Table loads in < 3 seconds
- Sortable by any column
- Default sort: Z-Score descending (biggest overperformers first)
- Flags trigger when |z_score| >= 1.5
- Min qualification: QB ≥ 100 dropbacks, WR/TE ≥ 20 targets, RB ≥ 40 carries

#### 4.2 Player Detail View
Clicking any player in the leaderboard opens a detail panel / page.

**Contains:**
- Player header (name, team, position, headshot)
- Week-by-week trend chart for the primary regression metric (actual vs. expected)
- Secondary metrics panel (all tracked metrics for this position, with z-scores)
- "Similar seasons" comps table (3–5 historical seasons with similar metric profiles)
- Short auto-generated insight text: "Patrick Mahomes is converting TDs at 8.2% on red zone
  targets vs. an expected rate of 5.1% (z=+2.1). Historically, QBs in this range regress
  to ~5.5% over the following 6 weeks."

#### 4.3 Position Scatter Plot
Interactive scatter for a selected position group showing two user-chosen metrics on X/Y axes.
Players plotted as dots; color = flag status; hover = player card tooltip.

### P1 — Secondary

#### 4.4 2026 Regression Outlook
Primary forward-looking view: regression candidates for `OUTLOOK_SEASON` (2026) based on
`ANALYSIS_SEASON` (2025) full-season metrics and v12 player tags. No 2026 stats are used.

**Inclusion:** `flag` in `OUTLOOK_REGRESSION_FLAGS`:
- `star` — sustainable high production + efficiency
- `breakout` — low role, high efficiency (role upside)
- `positive_outlook` — low production, high efficiency
- `regress_negative` — fade / negative regression risk (overperformance vs baseline)

**Team:** `projected_team` from `ROSTER_SEASON_FOR_OUTLOOK` (2025 seasonal rosters). Rookies excluded from scope.

**Columns:** Player, Pos, 2026 Team (projected), Outlook type, 2025 Z (`production_z`), primary metric, current/expected, flag.

Default sort: |composite z| descending (strongest signals first).

#### 4.5 Team-Level View
Aggregate regression risk by team. Bar chart showing net regression score per team
(sum of individual player `composite_z_adjusted` values). Useful for identifying game-week scheduling angles.

#### 4.6 Export
CSV download of the current leaderboard table (filtered or unfiltered).

---

## 5. Regression Metrics Specification

### 5.1 QB Metrics

| Metric ID | Name | Formula | Columns Used | Regression Logic |
|---|---|---|---|---|
| `qb_cpoe` | Completion % Over Expected | `complete_pass - cp` (per dropback, then sum/avg) | `complete_pass`, `cp` (NGS) | High CPOE sustainable ~30%; outliers regress |
| `qb_td_rate` | TD Rate vs. Opportunity | `pass_touchdown / (pass_attempt - sack)` vs. expected from `red_zone_target_share` | `pass_touchdown`, `pass_attempt`, `sack` | Red zone TDs are noisy; opportunity more predictive |
| `qb_adot` | Air Depth of Target | `air_yards / pass_attempt` | `air_yards`, `pass_attempt` | High aDOT with low CPOE = unsustainable efficiency |
| `qb_pressure_rate` | Pressure Rate | `was_pressure / dropbacks` | `was_pressure` | High pressure rate predicts performance decay |

### 5.2 WR / TE Metrics

| Metric ID | Name | Formula | Columns Used | Regression Logic |
|---|---|---|---|---|
| `recv_target_share` | Target Share | `targets / team_pass_attempts` (weekly) | `targets`, `posteam` | More stable than yards; yard/target regresses to mean |
| `recv_yac_oe` | YAC Over Expected | `yards_after_catch - xyac_mean_yardage` | `yards_after_catch`, `xyac_mean_yardage` | High YAC OE regresses; separation more durable |
| `recv_separation` | Average Separation | `avg_separation` (NGS receiving) | NGS `avg_separation` | Higher separation = more sustainable production |
| `recv_catch_rate_oe` | Catch Rate Over Expected | `receptions / targets` vs. `cp` average on targets | `receptions`, `targets`, `cp` | Similar to CPOE; luck in catch rate normalizes |
| `recv_td_share` | TD Share vs. Opportunity | `receiving_td / red_zone_targets` | `receiving_tds`, `red_zone_targets` | Red zone TDs noisy; target share in RZ more predictive |

### 5.3 RB Metrics

| Metric ID | Name | Formula | Columns Used | Regression Logic |
|---|---|---|---|---|
| `rb_ryoe` | Rushing Yards Over Expected | `rushing_yards - rushing_yards_over_expected` (NGS) | NGS `rushing_yards_over_expected` | Normalizes for blocking; high RYOE regresses |
| `rb_target_share` | Target Share | `targets / team_pass_attempts` | `targets` | More predictive of floor than carries |
| `rb_td_rate` | TD Rate vs. Opportunity | `rushing_tds / carries` vs. `red_zone_carry_share` | `rushing_tds`, `rush_attempt` | Goal-line TDs are volatile |
| `rb_breakaway_rate` | Breakaway Run Rate | `rush_20plus_yards / rush_attempt` | play-by-play filter | Boom/bust; mean-reverts quickly |

### 5.4 Z-Score Calculation

For each metric, compute a rolling z-score against the population of all qualifying
player-seasons from the baseline years (2023–2024). The current season (2025) is
excluded from the population so players are scored against prior-year distributions:

```python
from scipy import stats

def compute_z_score(player_value, population_values):
    mean = np.mean(population_values)
    std = np.std(population_values)
    if std == 0:
        return 0
    return (player_value - mean) / std
```

**v12 player tags** (via `assign_player_tag` in `calculator.py`; axis thresholds in `config.py`):
- `star`, `breakout`, `positive_outlook`, `regress_negative`, `neutral`
- Role / efficiency / production axis z-scores drive tagging; TD-luck metrics can adjust tags.

**Composite regression score (v12)**: `composite_z` and `composite_z_adjusted` equal `production_z`
(weighted production-axis score). Leaderboard sort, team net score, and 2026 outlook use this value.

**Legacy threshold**: `REGRESSION_Z_THRESHOLD` (1.28) remains for meta display and single-metric helpers;
primary UI flags use v12 tags above.

---

## 6. Data Model

### 6.1 Core DataFrames (in-memory at runtime)

**`df_players`** — one row per player per week per season
```
player_id       str     nfl_data_py gsis_id
player_name     str
position        str     QB | WR | RB | TE
team            str     team abbreviation
season          int
week            int
# ... all metric columns appended by metrics engine
```

**`df_metrics`** — one row per player per season (aggregated)
```
player_id
season
week_start / week_end   (range covered)
[metric_id]_value       float   (one column per metric above)
[metric_id]_z           float   (z-score vs. population)
composite_z             float   (weighted composite)
flag                    str     'regress_negative' | 'regress_positive' | 'neutral'
```

**`df_comps`** — historical comparable seasons
```
player_id
comp_player_id
comp_season
similarity_score    float   cosine similarity of metric vectors
```

### 6.2 Cache Files
```
/data/pbp_{year}.parquet
/data/weekly_{year}.parquet
/data/ngs_passing_{year}.parquet
/data/ngs_receiving_{year}.parquet
/data/ngs_rushing_{year}.parquet
/data/rosters_{year}.parquet
/data/metrics_computed.parquet   (output of metrics engine — refresh weekly)
```

---

## 7. App Structure

```
app.py                  Dash app init, layout router, server
config.py               Constants, thresholds, metric definitions
callbacks.py            All Dash callbacks (or split by page)

/data/                  Parquet cache files (git-ignored)
/metrics/
    __init__.py
    loader.py           Data fetching + cache logic
    calculator.py       Z-score + regression flag computation
    comps.py            Historical comparable season matching

/components/
    __init__.py
    leaderboard.py      Regression leaderboard table component
    outlook_2026.py     2026 regression outlook table
    player_detail.py    Player drill-down panel
    scatter.py          Position scatter plot
    team_view.py        Team net regression bar chart
    charts.py           Weekly volume trend chart (player detail)
    header.py           App header / nav

/assets/
    custom.css          Any style overrides on top of DBC DARKLY
```

---

## 8. Non-Functional Requirements

- **Performance**: App must load initial leaderboard in < 3s on first render after cache warm.
  Subsequent interactions (filter, sort, drill-down) must respond in < 500ms.
- **Caching**: `nfl_data_py` fetches are slow. Always check for a local Parquet file first.
  Use `functools.lru_cache` or Dash's `dcc.Store` for in-session caching.
- **No auth required**: Single-user local app or simple deployed instance.
- **Responsiveness**: Readable on 1440px desktop; mobile is not a priority.
- **Error handling**: If NGS data is unavailable for a metric, gracefully exclude that metric
  and note the gap in the UI rather than crashing.

---

## 9. Out of Scope (v1)

- Week-over-week (WoW) regression score deltas
- Year-over-year (YoY) season-to-season delta tables
- Real-time / live game data
- DFS lineup optimizer
- Betting odds integration
- User accounts / saved views
- Mobile-optimized layout
- Defensive player analysis
