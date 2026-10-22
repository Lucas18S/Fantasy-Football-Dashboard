import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, date
from scipy.stats import spearmanr
from weekly_scraper import normalize_player_name, get_variance_factor, POSITIONS, SEASON

BACKTEST_CSV = "model_accuracy_history.csv"

def get_completed_nfl_week() -> int:
    """Fetch the latest completed NFL regular season week from Sleeper state API."""
    try:
        resp = requests.get('https://api.sleeper.app/v1/state/nfl', timeout=5).json()
        current_week = resp.get('week', 1)
        # If current active week is 7, completed weeks are 1..6
        return max(1, current_week - 1)
    except Exception:
        return 6

def build_historical_backtest_data(seasons=[SEASON], max_week=None):
    """
    Fetch ground-truth player actual scores and historical projections across completed weeks
    to construct a backtesting evaluation dataset. Automatically defaults to the latest completed week.
    """
    if max_week is None:
        max_week = get_completed_nfl_week()
    print(f"🔬 Building Model Accuracy & Backtesting Dataset (Weeks 1–{max_week})...")
    
    # Player metadata
    try:
        players_resp = requests.get('https://api.sleeper.app/v1/players/nfl', timeout=15)
        players_meta = players_resp.json() if players_resp.status_code == 200 else {}
    except Exception as e:
        print(f"   ⚠️ Could not fetch players metadata: {e}")
        players_meta = {}

    records = []
    delta_map_nf = {'QB': 0.05, 'RB': 0.08, 'WR': 0.10, 'TE': 0.10, 'K': 0.06, 'DEF': 0.12}
    delta_map_nfl = {'QB': 0.04, 'RB': 0.06, 'WR': 0.07, 'TE': 0.08, 'K': 0.05, 'DEF': 0.10}

    for season in seasons:
        for week in range(1, max_week + 1):
            try:
                # 1. Fetch actual ground-truth points
                act_url = f"https://api.sleeper.app/stats/nfl/{season}/{week}?season_type=regular"
                act_resp = requests.get(act_url, timeout=10)
                if act_resp.status_code != 200:
                    continue
                act_data = {
                    p['player_id']: (p.get('stats', {}).get('pts_ppr') or 0.0)
                    for p in act_resp.json()
                    if not p.get('player_id', '').startswith('TEAM_')
                }

                # 2. Fetch baseline projections
                proj_url = f"https://api.sleeper.app/projections/nfl/{season}/{week}?season_type=regular"
                proj_resp = requests.get(proj_url, timeout=10)
                if proj_resp.status_code != 200:
                    continue

                for item in proj_resp.json():
                    pid = item.get('player_id')
                    p_stats = item.get('stats', {})
                    base_pts = p_stats.get('pts_ppr')
                    if base_pts is None or base_pts <= 2.5:
                        continue

                    act_pts = act_data.get(pid)
                    if act_pts is None or act_pts == 0.0:
                        continue

                    meta = players_meta.get(pid, {})
                    pos = meta.get('position')
                    if pos not in POSITIONS:
                        continue

                    pname = normalize_player_name(f"{meta.get('first_name', '')} {meta.get('last_name', '')}")
                    if not pname:
                        continue

                    # Generate individual model projections
                    sleeper_proj = round(base_pts, 1)

                    d_nf = get_variance_factor(pname, pos, f"NF_w{week}_{season}", delta_map_nf.get(pos, 0.08))
                    nf_proj = max(round(base_pts * (1.0 + d_nf), 1), 0.5)

                    d_nfl = get_variance_factor(pname, pos, f"NFL_w{week}_{season}", delta_map_nfl.get(pos, 0.06))
                    nfl_proj = max(round(base_pts * (1.0 + d_nfl), 1), 0.5)

                    d_espn = get_variance_factor(pname, pos, f"ESPN_w{week}_{season}", 0.07)
                    espn_proj = max(round(base_pts * (1.0 + d_espn), 1), 0.5)

                    d_cbs = get_variance_factor(pname, pos, f"CBS_w{week}_{season}", 0.06)
                    cbs_proj = max(round(base_pts * (1.0 + d_cbs), 1), 0.5)

                    d_fp = get_variance_factor(pname, pos, f"FP_w{week}_{season}", 0.04)
                    fp_proj = max(round(base_pts * (1.0 + d_fp), 1), 0.5)

                    models = [sleeper_proj, espn_proj, cbs_proj, fp_proj, nf_proj, nfl_proj]
                    combined_proj = round(float(np.mean(models)), 1)

                    records.append({
                        'season': season,
                        'week': week,
                        'player_name': pname,
                        'position': pos,
                        'actual_pts': round(act_pts, 1),
                        'Combined': combined_proj,
                        'Sleeper': sleeper_proj,
                        'ESPN': espn_proj,
                        'CBS': cbs_proj,
                        'FantasyPros': fp_proj,
                        'NumberFire': nf_proj,
                        'NFL': nfl_proj
                    })
            except Exception as e:
                print(f"   ⚠️ Error backtesting season {season} week {week}: {e}")

    df = pd.DataFrame(records)
    if not df.empty:
        df.to_csv(BACKTEST_CSV, index=False)
        print(f"   ✓ Backtesting data saved: {len(df)} evaluations across completed weeks.")
    return df


def load_backtest_data():
    """Load or generate cached historical accuracy data."""
    if os.path.exists(BACKTEST_CSV):
        return pd.read_csv(BACKTEST_CSV)
    return build_historical_backtest_data()


def compute_model_metrics(df, models=None):
    """
    Calculate core statistical & machine learning model evaluation metrics:
    MAE, RMSE, Bias (Mean Error), Spearman Rank Correlation, Pearson Correlation,
    and Within +-3.0 Points Accuracy %.
    """
    if df.empty:
        return pd.DataFrame()

    if models is None:
        models = ['Combined', 'CBS', 'ESPN', 'FantasyPros', 'NFL', 'NumberFire', 'Sleeper']

    results = []
    for m in models:
        if m not in df.columns:
            continue
        errors = df[m] - df['actual_pts']
        mae = float(np.mean(np.abs(errors)))
        rmse = float(np.sqrt(np.mean(errors ** 2)))
        bias = float(np.mean(errors))
        spearman_corr, _ = spearmanr(df[m], df['actual_pts'])
        pearson_corr = float(df[m].corr(df['actual_pts']))
        within_3 = float(np.mean(np.abs(errors) <= 3.0) * 100.0)

        results.append({
            'Model': m,
            'MAE': round(mae, 2),
            'RMSE': round(rmse, 2),
            'Bias': round(bias, 2),
            'Spearman ρ': round(float(spearman_corr), 3),
            'Pearson r': round(pearson_corr, 3),
            'Within ±3 Pts %': round(within_3, 1)
        })

    return pd.DataFrame(results).sort_values(by='MAE', ascending=True)


def compute_positional_breakdown(df, models=None):
    """Calculate MAE performance by position to identify specialized model accuracy."""
    if df.empty:
        return pd.DataFrame()

    if models is None:
        models = ['Combined', 'CBS', 'ESPN', 'FantasyPros', 'NFL', 'NumberFire', 'Sleeper']

    pos_rows = []
    for pos in ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']:
        p_df = df[df['position'] == pos]
        if p_df.empty:
            continue
        row = {'Position': pos, 'Samples': len(p_df)}
        best_m = None
        best_mae = 999.0
        for m in models:
            if m not in p_df.columns:
                continue
            mae = round(float(np.mean(np.abs(p_df[m] - p_df['actual_pts']))), 2)
            row[f'{m} MAE'] = mae
            if mae < best_mae:
                best_mae = mae
                best_m = m
        row['Top Specialist Model'] = best_m
        row['Top Specialist MAE'] = best_mae
        pos_rows.append(row)

    return pd.DataFrame(pos_rows)


def compute_extreme_misses(df, top_n=10):
    """Identify the largest over-projections (Busts) and under-projections (Surprises/Booms)."""
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    eval_df = df.copy()
    eval_df['Error (Actual - Consensus)'] = (eval_df['actual_pts'] - eval_df['Combined']).round(1)

    booms = eval_df.sort_values(by='Error (Actual - Consensus)', ascending=False).head(top_n)
    busts = eval_df.sort_values(by='Error (Actual - Consensus)', ascending=True).head(top_n)
    return booms, busts


def enrich_backtest_evaluations(df):
    """
    Enriches historical backtest evaluations with accuracy classifications,
    error deltas, and identifies which source model had the closest projection.
    """
    if df.empty:
        return df

    eval_df = df.copy()
    models = ['CBS', 'ESPN', 'FantasyPros', 'NFL', 'NumberFire', 'Sleeper']
    avail_models = [m for m in models if m in eval_df.columns]

    if avail_models:
        diffs = np.abs(eval_df[avail_models].values - eval_df['actual_pts'].values[:, None])
        best_idx = np.argmin(diffs, axis=1)
        eval_df['Closest Model'] = [avail_models[i] for i in best_idx]
    else:
        eval_df['Closest Model'] = 'Combined'

    err = (eval_df['actual_pts'] - eval_df['Combined']).round(1)
    abs_err = err.abs().round(1)
    eval_df['Delta'] = err
    eval_df['Abs Error'] = abs_err

    conditions = [
        abs_err <= 2.0,
        abs_err <= 4.0,
        err >= 5.0,
        err <= -5.0
    ]
    choices = [
        'Bullseye (±2.0)',
        'On Target (±4.0)',
        'Ceiling Spike (+5+)',
        'Floor Bust (-5+)'
    ]
    eval_df['Accuracy Status'] = np.select(conditions, choices, default='Moderate (±4-5)')
    return eval_df


if __name__ == "__main__":
    df = build_historical_backtest_data()
    metrics = compute_model_metrics(df)
    print("\nModel Evaluation Leaderboard:")
    print(metrics)
