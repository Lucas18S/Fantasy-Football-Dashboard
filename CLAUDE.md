# CLAUDE.md — Fantasy Football Decision Intelligence Platform

Welcome! This document provides context on the project's architecture, conventions, accomplishments, and current roadmap so development between Claude Code and Antigravity remains seamlessly aligned.

---

## 1. Project Overview & Tech Stack
- **Framework**: Python 3.9+ / Streamlit (version 1.50+)
- **Primary Domain**: Advanced Fantasy Football Analytics, Multi-Source Ensemble Forecasting, Strategic Trade Valuation, Head-to-Head Simulation, and Empirical Backtesting.
- **Supported League Platforms**: Sleeper API, ESPN Fantasy API (public and private leagues).
- **Core Market Sources**: FantasyCalc API, KeepTradeCut (KTC) market values & rookie draft picks.
- **Core Forecast Models (6 Sources)**: CBS Sports, ESPN, FantasyPros, NFL.com, NumberFire, Sleeper.
- **Data Persistence**: CSV caches (`projections_combined.csv`, `projections_combined_comparison.csv`, `model_accuracy_history.csv`), JSON local stores (`users.json`, `analytics.json`, `trade_values_cache.json`).
- **Cloud Backup**: Automated sync to Google Drive via `sync_to_gdrive.py`.

---

## 2. Core Architecture & Directory Layout

```
.
├── dashboard.py                  # Main Streamlit application (tabs, UI components, session state)
├── trade_engine.py               # Trade valuation engine, market parity, roster impact, trade suggestions
├── backtester.py                 # Ground-truth evaluation engine (MAE, RMSE, Spearman rho, positional specialists)
├── weekly_scraper.py             # Multi-source scraper & projection normalizer (CBS, ESPN, FP, NFL, NF, Sleeper)
├── auth_manager.py               # Authentication, bcrypt password hashing, persistent session tokens, role permissions
├── analytics_manager.py          # User engagement & telemetry logger (tab views, feature triggers)
├── sync_to_gdrive.py             # Google Drive API synchronization script for persistent backups
├── schedule_scraper.py           # Scheduled weekly scraper automation
├── users.json                    # Secure credential and session token store
├── analytics.json                # User interaction metrics
├── projections_combined.csv      # Consensus projections & floor/ceiling bands
├── projections_combined_comparison.csv # Side-by-side individual model projections
└── model_accuracy_history.csv    # Evaluated ground truth box scores across completed weeks
```

---

## 3. The 7 Dashboard Modules (Tabs)

1. **Lineup Optimizer**: Computes mathematically optimal starting rosters for any team in the league based on custom roster slots (QB, RB, WR, TE, FLEX, SUPER_FLEX, K, DEF). Displays efficiency deltas and bench promotions.
2. **Matchup Simulator**: Simulates weekly head-to-head league matchups using optimal lineup projections, floor/ceiling volatility bands, and logistic win probabilities. Includes a slot-by-slot matchup table.
3. **Trade Analyzer**: High-powered trade evaluation engine comparing market values (FantasyCalc/KTC), weekly lineup impact, dynasty draft picks, and generates strategic roster-balancing suggestions.
4. **Waiver Radar**: Scans unrostered free agents in the league, assigning volatility badges (`Ceiling Target`, `Stable Floor`, `Consensus Flex`, `Volatile Risk`, `Speculative Dart`).
5. **Projection Arbitrage Matrix**: Cross-examines individual models (CBS, ESPN, FantasyPros, NFL, NumberFire, Sleeper) to isolate high-disagreement players (underdog boom candidates) vs strong-consensus players (safe floor starters).
6. **Position Consensus Tiers**: Groups players into distinct tier buckets per position based on point spread falloffs with weekly opponent context.
7. **Model Backtesting**: Evaluates forecast models against ground-truth NFL box-score points across completed weeks. Analyzes MAE, RMSE, systematic model bias, rank correlation (Spearman $\rho$), and positional specialist models.
8. **Admin Console** *(Role-restricted to admin)*: User management, persistent league purging, feature usage analytics, and maintenance tools.

---

## 4. Established Conventions & Critical Rules

### Rule A: "Analyze Trade" On-Demand Calculation
- Trade evaluations and balancing suggestions **must never run automatically on multiselect change**.
- Recalculation runs **only** when the user clicks the primary `"Analyze Trade"` button (exact text, no emojis).
- Keep the `Clear` button using the callback `on_click=clear_trade_selection` to reset state **before** widgets instantiate.
- Multiselects use `on_change=clean_headers_a/b` to automatically purge header labels (`━━━ POS ━━━`) from selections.
- **Never mutate widget session keys** after widget instantiation to avoid `StreamlitWidgetAlreadyInstantiatedError`.

### Rule B: Opponent Notation Convention
- Players across Optimizer, Matchups, Waiver Radar, Arbitrage, and Position Tiers display opponent matchups.
- **Home games**: Displayed as bare opponent abbreviation (e.g. `KC`, `SF`, `DAL`). Do **not** prefix with "H" or "vs".
- **Away games**: Displayed with an `@` prefix (e.g. `@BUF`, `@PHI`).
- Bye weeks: Displayed as `BYE`. Unmatched: `—`.

### Rule C: Streamlit Performance & Caching
- Streamlit reruns `dashboard.py` top-to-bottom on any widget interaction.
- Heavy data transformations (projection parsing, variance calculations, arbitrage pivots, backtester metrics) **must be decorated with `@st.cache_data(ttl=..., show_spinner=False)`**.
- **Never use Python `id()`** (such as `id(market_data)` or `id(df)`) as memoization cache keys because Streamlit deserializes cached objects on each rerun, yielding new memory addresses and causing cache misses. Always use value-based keys (e.g. `(tuple(pids), is_dynasty, qbs, ppr)`).
- When iterating over DataFrames, prefer `.itertuples(index=False)` or dictionary lookups over `.iterrows()`.

### Rule D: Persistent Authentication
- Users are authenticated via `auth_manager.py`.
- Session tokens are stored in `st.query_params["session"]` and `localStorage`, enabling persistent login across page refreshes.
- Role checks: `auth_manager.is_admin(username)`.

---

## 5. Recent Accomplishments
- Replaced auto-recalculation in Trade Analyzer with explicit `"Analyze Trade"` button and zero-lag asset selection.
- Eliminated `StreamlitWidgetAlreadyInstantiatedError` via atomic callbacks.
- Standardized NFL opponent indicators across all 5 player-facing tabs (`KC` for home, `@BUF` for away).
- Optimized rerun latency from ~1.5 seconds down to < 20ms using vectorized lookups and stable `@st.cache_data` tables.
- Built automated Google Drive cloud backup pipeline (`sync_to_gdrive.py`) running on daily daemon schedule.
- Implemented automated daily scraping pipeline (`schedule_scraper.py`) via native macOS LaunchAgent (`com.fantasy.scraper.daily.plist`) executing daily at 7:00 AM + game-day cycles, followed immediately by automatic cloud backup sync.
- Added in-dashboard 1-click "Refresh Now" button for on-demand mid-day projection updates.

---

## 6. Where We Are Headed (Roadmap & Next Steps)
1. **Multi-Team Trade Analyzer**: Expanding trade analysis beyond 2-team trades to support 3-way dynasty blockbuster trades.
2. **FAAB / Waiver Budget Recommendation Engine**: Adding dynamic FAAB dollar bid suggestions based on roster need, market value, and remaining league FAAB budgets.
3. **Automated Weekly Report / Export**: Generating downloadable PDF / Markdown weekly executive summaries for league managers.
4. **Additional Platform Support**: Extending league connectors beyond Sleeper & ESPN to include Yahoo Fantasy and NFL.com.
5. **Real-Time Injury Ingestion**: Auto-incorporating Sleeper official injury designations (`OUT`, `QUESTIONABLE`, `IR`) into the Lineup Optimizer and Trade Impact calculations.
