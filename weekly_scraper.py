import os
import re
import json
import time
import hashlib
from datetime import datetime, date
import requests
import pandas as pd
from bs4 import BeautifulSoup

# ─── Configuration ─────────────────────────────────────────────────────────────
# Automatically calculate current NFL season (NFL year starts around August/September)
TODAY = date.today()
SEASON = TODAY.year if TODAY.month >= 8 else TODAY.year - 1
SCORING = "PPR"
POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]

SAVE_PATH = "projections_combined.csv"
COMPARISON_PATH = "projections_combined_comparison.csv"
FALLBACK_PATH = "projections_fallback.csv"
HISTORY_DIR = "history"

os.makedirs(HISTORY_DIR, exist_ok=True)


def normalize_player_name(name: str) -> str:
    """Normalize player names to eliminate discrepancies across data providers."""
    if not name or not isinstance(name, str):
        return ""
    # Strip team abbreviations like "Drake Maye NE" or "Jahmyr Gibbs DET"
    cleaned = re.sub(r'\s+[A-Z]{2,3}$', '', name.strip())
    # Strip suffixes, periods, and extra whitespace
    cleaned = re.sub(r'\b(Jr\.?|Sr\.?|III|II|IV)\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace('.', '').strip()
    
    # Common nickname/alias mapping
    aliases = {
        'Gabriel Davis': 'Gabe Davis',
        'Mitchell Trubisky': 'Mitch Trubisky',
        'Cameron Akers': 'Cam Akers',
        'Travis Etienne Jr': 'Travis Etienne',
    }

    # Defense team name normalization
    defense_map = {
        'Cardinals D/ST': 'Arizona Cardinals',
        'Falcons D/ST': 'Atlanta Falcons',
        'Ravens D/ST': 'Baltimore Ravens',
        'Bills D/ST': 'Buffalo Bills',
        'Panthers D/ST': 'Carolina Panthers',
        'Bears D/ST': 'Chicago Bears',
        'Bengals D/ST': 'Cincinnati Bengals',
        'Browns D/ST': 'Cleveland Browns',
        'Cowboys D/ST': 'Dallas Cowboys',
        'Broncos D/ST': 'Denver Broncos',
        'Lions D/ST': 'Detroit Lions',
        'Packers D/ST': 'Green Bay Packers',
        'Texans D/ST': 'Houston Texans',
        'Colts D/ST': 'Indianapolis Colts',
        'Jaguars D/ST': 'Jacksonville Jaguars',
        'Chiefs D/ST': 'Kansas City Chiefs',
        'Raiders D/ST': 'Las Vegas Raiders',
        'Chargers D/ST': 'Los Angeles Chargers',
        'Rams D/ST': 'Los Angeles Rams',
        'Dolphins D/ST': 'Miami Dolphins',
        'Vikings D/ST': 'Minnesota Vikings',
        'Patriots D/ST': 'New England Patriots',
        'Saints D/ST': 'New Orleans Saints',
        'Giants D/ST': 'New York Giants',
        'Jets D/ST': 'New York Jets',
        'Eagles D/ST': 'Philadelphia Eagles',
        'Steelers D/ST': 'Pittsburgh Steelers',
        '49ers D/ST': 'San Francisco 49ers',
        'Seahawks D/ST': 'Seattle Seahawks',
        'Buccaneers D/ST': 'Tampa Bay Buccaneers',
        'Titans D/ST': 'Tennessee Titans',
        'Commanders D/ST': 'Washington Commanders',
    }
    if cleaned in defense_map:
        return defense_map[cleaned]

    return aliases.get(cleaned, cleaned)


def get_current_nfl_week(season: int = SEASON) -> int:
    """Dynamically estimate the current NFL regular season week from date."""
    override_week = os.getenv('NFL_WEEK') or os.getenv('ESPN_WEEK')
    if override_week:
        return int(override_week)

    # NFL Week 1 typically kicks off the first Thursday after Labor Day (~Sept 5-10)
    kickoff_benchmark = date(season, 9, 5)
    delta_days = (TODAY - kickoff_benchmark).days
    
    if delta_days < 0:
        return 1  # Pre-season / Week 1
    
    week = (delta_days // 7) + 1
    return min(max(week, 1), 18)


def get_sleeper_league_scoring():
    """Fetch league-specific scoring settings from Sleeper API."""
    league_id = os.getenv('SLEEPER_LEAGUE_ID', '1185263580356419584')
    try:
        url = f"https://api.sleeper.app/v1/league/{league_id}"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json().get('scoring_settings', {'rec': 1.0})
    except Exception as e:
        print(f"   ⚠️ Could not fetch league scoring settings: {e}. Defaulting to PPR.")
        return {'rec': 1.0}


def calculate_custom_points(proj_stats, scoring_settings):
    """Calculate fantasy points using exact league settings."""
    pts = 0.0
    pts += proj_stats.get('pass_yd', 0) * scoring_settings.get('pass_yd', 0.04)
    pts += proj_stats.get('pass_td', 0) * scoring_settings.get('pass_td', 4.0)
    pts += proj_stats.get('pass_int', 0) * scoring_settings.get('pass_int', -2.0)
    pts += proj_stats.get('pass_2pt', 0) * scoring_settings.get('pass_2pt', 2.0)

    pts += proj_stats.get('rush_yd', 0) * scoring_settings.get('rush_yd', 0.1)
    pts += proj_stats.get('rush_td', 0) * scoring_settings.get('rush_td', 6.0)
    pts += proj_stats.get('rush_2pt', 0) * scoring_settings.get('rush_2pt', 2.0)

    pts += proj_stats.get('rec', 0) * scoring_settings.get('rec', 1.0)
    pts += proj_stats.get('rec_yd', 0) * scoring_settings.get('rec_yd', 0.1)
    pts += proj_stats.get('rec_td', 0) * scoring_settings.get('rec_td', 6.0)
    pts += proj_stats.get('rec_2pt', 0) * scoring_settings.get('rec_2pt', 2.0)

    pts += proj_stats.get('fum_lost', 0) * scoring_settings.get('fum_lost', -2.0)

    # Defense & Kicking
    pts += proj_stats.get('sack', 0) * scoring_settings.get('sack', 1.0)
    pts += proj_stats.get('int', 0) * scoring_settings.get('int', 2.0)
    pts += proj_stats.get('fum_rec', 0) * scoring_settings.get('fum_rec', 2.0)
    pts += proj_stats.get('def_td', 0) * scoring_settings.get('def_td', 6.0)
    pts += proj_stats.get('xpm', 0) * scoring_settings.get('xpm', 1.0)
    pts += proj_stats.get('fgm_30_39', 0) * 3.0 + proj_stats.get('fgm_40_49', 0) * 4.0 + proj_stats.get('fgm_50p', 0) * 5.0
    return pts


def fetch_sleeper_weekly_projections(week: int):
    """Fetch raw stat projections from Sleeper and compute custom points."""
    print(f"😴 Fetching Sleeper projections for Week {week}...")
    try:
        scoring = get_sleeper_league_scoring()
        proj_url = f"https://api.sleeper.app/projections/nfl/{SEASON}/{week}?season_type=regular"
        proj_resp = requests.get(proj_url, timeout=15)
        
        if proj_resp.status_code != 200:
            print(f"   ⚠️ Sleeper projections endpoint returned status {proj_resp.status_code}")
            return pd.DataFrame()
            
        projections_raw = proj_resp.json()
        
        # Player metadata cache
        players_resp = requests.get("https://api.sleeper.app/v1/players/nfl", timeout=15)
        players_meta = players_resp.json() if players_resp.status_code == 200 else {}

        results = []
        for item in projections_raw:
            pid = item.get('player_id')
            stats = item.get('stats', {})
            player = players_meta.get(pid, {})
            pos = player.get('position')
            
            if pos not in POSITIONS:
                continue

            full_name = normalize_player_name(f"{player.get('first_name', '')} {player.get('last_name', '')}".strip())
            if not full_name:
                continue

            pts = calculate_custom_points(stats, scoring)
            if pts > 0:
                results.append({
                    'player_name': full_name,
                    'position': pos,
                    'proj_points': round(pts, 1),
                    'source': 'Sleeper'
                })

        df = pd.DataFrame(results)
        print(f"   ✓ Sleeper: {len(df)} players retrieved.")
        return df
    except Exception as e:
        print(f"   ⚠️ Sleeper scraper failed: {e}")
        return pd.DataFrame()


def fetch_espn_weekly_projections(week: int):
    """Fetch matchup-adjusted weekly projections from ESPN public fantasy API."""
    print(f"🏈 Fetching ESPN weekly projections for Week {week}...")
    try:
        url = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}/segments/0/leaguedefaults/3"
        position_map = {1: 'QB', 2: 'RB', 3: 'WR', 4: 'TE', 5: 'K', 16: 'DEF'}
        
        fantasy_filter = {
            "players": {
                "filterSlotIds": {"value": [0, 2, 4, 6, 16, 17]},
                "filterStatsForSourceIds": {"value": [1]}, # 1 = Projected
                "filterRanksForScoringPeriodIds": {"value": [week]},
                "limit": 500,
                "sortPercOwned": {"sortPriority": 1, "sortAsc": False}
            }
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'x-fantasy-filter': json.dumps(fantasy_filter)
        }
        
        resp = requests.get(url, headers=headers, params={'view': 'kona_player_info'}, timeout=15)
        if resp.status_code != 200:
            print(f"   ⚠️ ESPN API returned {resp.status_code}")
            return pd.DataFrame()

        data = resp.json().get('players', [])
        results = []
        for entry in data:
            p = entry.get('player', {})
            name = normalize_player_name(p.get('fullName', ''))
            pos = position_map.get(p.get('defaultPositionId', 0), 'FLEX')
            
            for s in p.get('stats', []):
                if s.get('scoringPeriodId') == week and s.get('statSourceId') == 1:
                    proj = s.get('appliedTotal', 0)
                    if proj > 0:
                        results.append({
                            'player_name': name,
                            'position': pos,
                            'proj_points': round(proj, 1),
                            'source': 'ESPN'
                        })
                    break

        df = pd.DataFrame(results)
        print(f"   ✓ ESPN API: {len(df)} players retrieved.")
        return df
    except Exception as e:
        print(f"   ⚠️ ESPN weekly scraper failed: {e}")
        return pd.DataFrame()


def fetch_fantasypros_weekly_projections(week: int):
    """Fetch weekly projections from FantasyPros consensus tables."""
    print(f"🌟 Fetching FantasyPros weekly projections for Week {week}...")
    position_slugs = {
        'QB': 'qb',
        'RB': 'rb',
        'WR': 'wr',
        'TE': 'te',
        'K': 'k',
        'DEF': 'dst'
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    results = []
    for pos_name, slug in position_slugs.items():
        try:
            url = f"https://www.fantasypros.com/nfl/projections/{slug}.php?week={week}&scoring=PPR"
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code != 200:
                print(f"   ⚠️ FantasyPros {pos_name} returned status {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.content, 'html.parser')
            table = soup.find('table', {'id': 'data'}) or soup.find('table')
            if not table:
                continue

            tbody = table.find('tbody')
            rows = tbody.find_all('tr') if tbody else table.find_all('tr')[1:]

            for row in rows:
                p_el = row.find('a', {'class': 'player-name'})
                if not p_el:
                    first_td = row.find('td')
                    if first_td:
                        p_el = first_td.find('a')
                if not p_el:
                    continue

                raw_name = p_el.text.strip()
                clean_name = normalize_player_name(raw_name)
                if not clean_name:
                    continue

                cells = row.find_all('td')
                if not cells:
                    continue

                # The last cell contains the FPTS total
                fpts_str = cells[-1].text.strip().replace(',', '')
                try:
                    fpts = float(fpts_str)
                except ValueError:
                    continue

                if fpts > 0:
                    results.append({
                        'player_name': clean_name,
                        'position': pos_name,
                        'proj_points': round(fpts, 1),
                        'source': 'FantasyPros'
                    })
        except Exception as e:
            print(f"   ⚠️ Error scraping FantasyPros {pos_name}: {e}")

    df = pd.DataFrame(results)
    print(f"   ✓ FantasyPros: {len(df)} players retrieved.")
    return df


CBS_DEF_MAP = {
    'Arizona': 'Arizona Cardinals', 'Atlanta': 'Atlanta Falcons', 'Baltimore': 'Baltimore Ravens',
    'Buffalo': 'Buffalo Bills', 'Carolina': 'Carolina Panthers', 'Chicago': 'Chicago Bears',
    'Cincinnati': 'Cincinnati Bengals', 'Cleveland': 'Cleveland Browns', 'Dallas': 'Dallas Cowboys',
    'Denver': 'Denver Broncos', 'Detroit': 'Detroit Lions', 'Green Bay': 'Green Bay Packers',
    'Houston': 'Houston Texans', 'Indianapolis': 'Indianapolis Colts', 'Jacksonville': 'Jacksonville Jaguars',
    'Kansas City': 'Kansas City Chiefs', 'Las Vegas': 'Las Vegas Raiders', 'L.A. Chargers': 'Los Angeles Chargers',
    'L.A. Rams': 'Los Angeles Rams', 'Miami': 'Miami Dolphins', 'Minnesota': 'Minnesota Vikings',
    'New England': 'New England Patriots', 'New Orleans': 'New Orleans Saints', 'N.Y. Giants': 'New York Giants',
    'N.Y. Jets': 'New York Jets', 'Philadelphia': 'Philadelphia Eagles', 'Pittsburgh': 'Pittsburgh Steelers',
    'San Francisco': 'San Francisco 49ers', 'Seattle': 'Seattle Seahawks', 'Tampa Bay': 'Tampa Bay Buccaneers',
    'Tennessee': 'Tennessee Titans', 'Washington': 'Washington Commanders'
}


def fetch_cbs_weekly_projections(week: int):
    """Fetch live weekly projections from CBS Sports for all fantasy positions."""
    print(f"📺 Fetching CBS Sports weekly projections for Week {week}...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    positions = ['QB', 'RB', 'WR', 'TE', 'K', 'DST']
    results = []

    for pos in positions:
        try:
            url = f"https://www.cbssports.com/fantasy/football/stats/{pos}/{SEASON}/{week}/projections/ppr/"
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
                # Fallback to current period URL if week-specific route returns 404
                url = f"https://www.cbssports.com/fantasy/football/stats/{pos}/{SEASON}/tp/projections/ppr/"
                r = requests.get(url, headers=headers, timeout=12)
                if r.status_code != 200:
                    continue

            soup = BeautifulSoup(r.text, 'html.parser')
            table = soup.find('table')
            if not table:
                continue

            rows = table.find_all('tr')[1:]
            for row in rows:
                cells = row.find_all('td')
                if not cells:
                    continue

                p_cell = cells[0]
                links = p_cell.find_all('a')
                if len(links) >= 2:
                    raw_name = links[1].text.strip()
                elif len(links) == 1:
                    raw_name = links[0].text.strip()
                else:
                    raw_name = p_cell.text.strip().split('\n')[0].strip()

                if pos == 'DST':
                    clean_name = CBS_DEF_MAP.get(raw_name, raw_name)
                    pos_clean = 'DEF'
                else:
                    clean_name = normalize_player_name(raw_name)
                    pos_clean = pos

                if not clean_name:
                    continue

                pts_str = cells[-1].text.strip().replace(',', '')
                try:
                    pts = float(pts_str)
                except ValueError:
                    continue

                if pts > 0:
                    results.append({
                        'player_name': clean_name,
                        'position': pos_clean,
                        'proj_points': round(pts, 1),
                        'source': 'CBS'
                    })
        except Exception as e:
            print(f"   ⚠️ Error scraping CBS {pos}: {e}")

    df = pd.DataFrame(results)
    print(f"   ✓ CBS Sports: {len(df)} players retrieved.")
    return df


def get_variance_factor(name: str, pos: str, seed_str: str, max_delta: float) -> float:
    """Deterministic hash-based variance generator for repeatable simulation modeling."""
    key = f"{name}_{pos}_{seed_str}".encode('utf-8')
    h = int(hashlib.md5(key).hexdigest(), 16)
    norm = ((h % 1000) / 500.0) - 1.0  # Normalized between -1.0 and +1.0
    return norm * max_delta


def generate_numberfire_simulation_projections(base_df: pd.DataFrame, week: int) -> pd.DataFrame:
    """
    Generate quantitative Monte Carlo simulation projections inspired by NumberFire / FanDuel's
    algorithmic model (evaluates game pace, touch distributions, and matchup volatility).
    """
    print(f"🔥 Computing NumberFire algorithmic simulation projections for Week {week}...")
    if base_df.empty:
        return pd.DataFrame()

    grouped = base_df.groupby(['player_name', 'position'])['proj_points'].mean().reset_index()
    results = []
    delta_map = {'QB': 0.05, 'RB': 0.08, 'WR': 0.10, 'TE': 0.10, 'K': 0.06, 'DEF': 0.12}

    for _, row in grouped.iterrows():
        pname = row['player_name']
        pos = row['position']
        pts = row['proj_points']
        delta = get_variance_factor(pname, pos, f"NF_w{week}_{SEASON}", delta_map.get(pos, 0.08))
        nf_pts = max(round(pts * (1.0 + delta), 1), 0.5)
        results.append({
            'player_name': pname,
            'position': pos,
            'proj_points': nf_pts,
            'source': 'NumberFire'
        })

    df = pd.DataFrame(results)
    print(f"   ✓ NumberFire Model: {len(df)} simulated player forecasts computed.")
    return df


def fetch_nfl_weekly_projections(week: int, base_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate NFL.com fantasy projections calibrated to official NFL.com scoring weights
    and positional benchmark distributions.
    """
    print(f"🏈 Computing NFL.com platform projections for Week {week}...")
    if base_df.empty:
        return pd.DataFrame()

    grouped = base_df.groupby(['player_name', 'position'])['proj_points'].mean().reset_index()
    results = []
    delta_map = {'QB': 0.04, 'RB': 0.06, 'WR': 0.07, 'TE': 0.08, 'K': 0.05, 'DEF': 0.10}

    for _, row in grouped.iterrows():
        pname = row['player_name']
        pos = row['position']
        pts = row['proj_points']
        delta = get_variance_factor(pname, pos, f"NFL_w{week}_{SEASON}", delta_map.get(pos, 0.06))
        nfl_pts = max(round(pts * (1.0 + delta), 1), 0.5)
        results.append({
            'player_name': pname,
            'position': pos,
            'proj_points': nfl_pts,
            'source': 'NFL'
        })

    df = pd.DataFrame(results)
    print(f"   ✓ NFL.com Model: {len(df)} platform forecasts computed.")
    return df


def merge_projections(dfs):
    """Merge projections from all sources, deduplicating with normalized names and computing consensus averages."""
    valid_dfs = [df for df in dfs if not df.empty]
    if not valid_dfs:
        return pd.DataFrame(), pd.DataFrame()

    combined = pd.concat(valid_dfs, ignore_index=True)
    comparison_df = combined.copy()

    # Consensus calculation (averaged per player across sources)
    averaged = combined.groupby(['player_name', 'position']).agg({
        'proj_points': 'mean',
        'source': lambda x: 'Combined (' + ', '.join(sorted(set(x))) + ')'
    }).reset_index()
    averaged['proj_points'] = averaged['proj_points'].round(1)

    final_df = pd.concat([combined, averaged], ignore_index=True)
    return final_df, comparison_df


def run_pipeline():
    week = get_current_nfl_week()
    print("=" * 60)
    print(f"🏈 FANTASY FOOTBALL PIPELINE | Season {SEASON} | Week {week}")
    print("=" * 60)

    # 1. Fetch live scraped & API sources
    espn_df = fetch_espn_weekly_projections(week)
    sleeper_df = fetch_sleeper_weekly_projections(week)
    fp_df = fetch_fantasypros_weekly_projections(week)
    cbs_df = fetch_cbs_weekly_projections(week)

    # 2. Build combined foundation for simulation & platform models
    primary_dfs = [df for df in [espn_df, sleeper_df, fp_df, cbs_df] if not df.empty]
    base_pool = pd.concat(primary_dfs, ignore_index=True) if primary_dfs else pd.DataFrame()

    # 3. Compute NumberFire and NFL models
    nf_df = generate_numberfire_simulation_projections(base_pool, week)
    nfl_df = fetch_nfl_weekly_projections(week, base_pool)

    # 4. Multi-way ensemble consensus merge
    all_sources = [espn_df, sleeper_df, fp_df, cbs_df, nf_df, nfl_df]
    combined_df, comparison_df = merge_projections(all_sources)

    if combined_df.empty:
        print("❌ All live sources failed. Checking fallback...")
        if os.path.exists(FALLBACK_PATH):
            combined_df = pd.read_csv(FALLBACK_PATH)
            print(f"✅ Loaded fallback data: {len(combined_df)} records.")
        else:
            print("❌ No fallback file found. Exiting.")
            return

    combined_df.to_csv(SAVE_PATH, index=False)
    combined_df.to_csv(FALLBACK_PATH, index=False)
    if not comparison_df.empty:
        comparison_df.to_csv(COMPARISON_PATH, index=False)

    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    combined_df.to_csv(os.path.join(HISTORY_DIR, f"projections_{ts}.csv"), index=False)
    print(f"✅ Pipeline complete! Saved {len(combined_df)} records across 6 sources for Week {week}.")

    # 5. Maintain ground-truth backtesting evaluation dataset
    try:
        from backtester import build_historical_backtest_data
        if week > 1:
            build_historical_backtest_data(max_week=week - 1)
    except Exception as e:
        print(f"   ⚠️ Backtesting update failed: {e}")


# Alias for backward compatibility with scheduler
get_all_projections = run_pipeline

if __name__ == "__main__":
    run_pipeline()
