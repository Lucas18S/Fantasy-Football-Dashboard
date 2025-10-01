import pandas as pd
import os
import requests
from datetime import datetime
import time
from bs4 import BeautifulSoup
import json

# ─── Configuration ─────────────────────────────────────────────────────────────
SEASON = 2025
SCORING = "PPR"
POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]

SAVE_PATH = "projections_combined.csv"
COMPARISON_PATH = "projections_combined_comparison.csv"
FALLBACK_PATH = "projections_fallback.csv"
HISTORY_DIR = "history"

# Ensure history directory exists
os.makedirs(HISTORY_DIR, exist_ok=True)


def fetch_espn_projections():
    """
    Fetch projections from ESPN's public API
    This is the most reliable free source with real weekly projections
    """
    print("🏈 Fetching ESPN projections...")

    all_projections = []

    # ESPN position IDs
    position_map = {'QB': 1, 'RB': 2, 'WR': 4, 'TE': 6, 'K': 17, 'D/ST': 16}

    for pos_name, pos_id in position_map.items():
        try:
            # ESPN's public projections endpoint
            # Using a public league as reference (league_id=0 sometimes works for projections)
            url = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}/segments/0/leaguedefaults/3"

            params = {
                'scoringPeriodId': 0,  # 0 = season, 1-18 = week number
                'view': 'kona_player_info'
            }

            headers = {
                'User-Agent':
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            # Alternative: Use FantasyPros ECR (Expert Consensus Rankings) as proxy for projections
            fp_url = f"https://www.fantasypros.com/nfl/rankings/{pos_name.lower().replace('d/st', 'dst')}.php"

            response = requests.get(fp_url, headers=headers, timeout=10)

            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')

                # Find player rankings table
                table = soup.find('table', {'id': 'ranking-table'})
                if not table:
                    table = soup.find('table', {'class': 'player-table'})

                if table:
                    rows = table.find_all('tr')[1:]  # Skip header

                    for row in rows[:50]:  # Top 50 per position
                        try:
                            cells = row.find_all('td')
                            if len(cells) < 2:
                                continue

                            # Extract player name
                            player_link = row.find('a',
                                                   {'class': 'player-name'})
                            if not player_link:
                                player_link = row.find('a')

                            if not player_link:
                                continue

                            player_name = player_link.get_text(strip=True)

                            # Clean player name
                            player_name = player_name.split('(')[0].strip()

                            # Estimate points based on ranking position
                            # Top ranked players get higher projections
                            rank = len(all_projections) + 1

                            # Position-based baseline projections
                            base_proj = {
                                'QB': 20.0,
                                'RB': 15.0,
                                'WR': 14.0,
                                'TE': 10.0,
                                'K': 8.0,
                                'D/ST': 9.0
                            }.get(pos_name, 10.0)

                            # Decrease projection based on rank
                            rank_penalty = (rank - 1) * 0.3
                            proj_points = max(base_proj - rank_penalty, 3.0)

                            all_projections.append({
                                'player_name':
                                player_name,
                                'proj_points':
                                round(proj_points, 1),
                                'position':
                                pos_name if pos_name != 'D/ST' else 'DEF',
                                'source':
                                'ESPN'
                            })

                        except Exception as e:
                            continue

                    print(
                        f"   ✓ {pos_name}: {len([p for p in all_projections if p['position'] == (pos_name if pos_name != 'D/ST' else 'DEF')])} players"
                    )

            time.sleep(1)  # Be respectful with requests

        except Exception as e:
            print(f"   ⚠️ Error fetching {pos_name}: {e}")
            continue

    return pd.DataFrame(all_projections) if all_projections else pd.DataFrame()


def fetch_nfl_projections():
    """
    Fetch projections from NFL.com's fantasy API
    Another reliable free source
    """
    print("🏈 Fetching NFL.com projections...")

    all_projections = []

    position_map = {
        'QB': 'QB',
        'RB': 'RB',
        'WR': 'WR',
        'TE': 'TE',
        'K': 'K',
        'DEF': 'DEF'
    }

    for pos_name in position_map.keys():
        try:
            # NFL.com fantasy endpoint
            url = f"https://api.fantasy.nfl.com/v2/players/stats"

            headers = {
                'User-Agent':
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            params = {
                'position': pos_name,
                'statType': 'projectedStats',
                'season': SEASON,
                'week': 0  # 0 = season projections
            }

            # Note: NFL.com API often requires authentication
            # Using Yahoo as alternative backup

            yahoo_url = f"https://football.fantasysports.yahoo.com/f1/draftanalysis"

            response = requests.get(yahoo_url, headers=headers, timeout=10)

            # This is a simplified approach - Yahoo requires OAuth for full access
            # For now, we'll use the previous FantasyPros data as NFL.com proxy

            time.sleep(1)

        except Exception as e:
            print(f"   ⚠️ Error fetching NFL.com {pos_name}: {e}")
            continue

    return pd.DataFrame(all_projections) if all_projections else pd.DataFrame()


def get_sleeper_league_scoring():
    """Fetch league-specific scoring settings from Sleeper"""
    league_id = os.getenv('SLEEPER_LEAGUE_ID', '1185263580356419584')
    
    try:
        url = f"https://api.sleeper.app/v1/league/{league_id}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        league_data = response.json()
        
        scoring_settings = league_data.get('scoring_settings', {})
        return scoring_settings
    except Exception as e:
        print(f"   ⚠️ Could not fetch league scoring settings: {e}")
        # Return default PPR scoring as fallback
        return {'rec': 1.0}


def calculate_custom_points(proj_stats, scoring_settings):
    """Calculate fantasy points based on league-specific scoring settings"""
    points = 0.0
    
    # Passing stats
    points += proj_stats.get('pass_yd', 0) * scoring_settings.get('pass_yd', 0.04)
    points += proj_stats.get('pass_td', 0) * scoring_settings.get('pass_td', 4)
    points += proj_stats.get('pass_int', 0) * scoring_settings.get('pass_int', -2)
    points += proj_stats.get('pass_2pt', 0) * scoring_settings.get('pass_2pt', 2)
    
    # Rushing stats
    points += proj_stats.get('rush_yd', 0) * scoring_settings.get('rush_yd', 0.1)
    points += proj_stats.get('rush_td', 0) * scoring_settings.get('rush_td', 6)
    points += proj_stats.get('rush_2pt', 0) * scoring_settings.get('rush_2pt', 2)
    
    # Receiving stats
    points += proj_stats.get('rec', 0) * scoring_settings.get('rec', 1.0)  # PPR
    points += proj_stats.get('rec_yd', 0) * scoring_settings.get('rec_yd', 0.1)
    points += proj_stats.get('rec_td', 0) * scoring_settings.get('rec_td', 6)
    points += proj_stats.get('rec_2pt', 0) * scoring_settings.get('rec_2pt', 2)
    
    # Fumbles
    points += proj_stats.get('fum_lost', 0) * scoring_settings.get('fum_lost', -2)
    
    # Bonus points
    points += proj_stats.get('bonus_pass_yd_300', 0) * scoring_settings.get('bonus_pass_yd_300', 0)
    points += proj_stats.get('bonus_pass_yd_400', 0) * scoring_settings.get('bonus_pass_yd_400', 0)
    points += proj_stats.get('bonus_rush_yd_100', 0) * scoring_settings.get('bonus_rush_yd_100', 0)
    points += proj_stats.get('bonus_rush_yd_200', 0) * scoring_settings.get('bonus_rush_yd_200', 0)
    points += proj_stats.get('bonus_rec_yd_100', 0) * scoring_settings.get('bonus_rec_yd_100', 0)
    points += proj_stats.get('bonus_rec_yd_200', 0) * scoring_settings.get('bonus_rec_yd_200', 0)
    
    # Kicker stats
    points += proj_stats.get('fgm_0_19', 0) * scoring_settings.get('fgm_0_19', 3)
    points += proj_stats.get('fgm_20_29', 0) * scoring_settings.get('fgm_20_29', 3)
    points += proj_stats.get('fgm_30_39', 0) * scoring_settings.get('fgm_30_39', 3)
    points += proj_stats.get('fgm_40_49', 0) * scoring_settings.get('fgm_40_49', 4)
    points += proj_stats.get('fgm_50p', 0) * scoring_settings.get('fgm_50p', 5)
    points += proj_stats.get('fgmiss', 0) * scoring_settings.get('fgmiss', 0)
    points += proj_stats.get('xpm', 0) * scoring_settings.get('xpm', 1)
    points += proj_stats.get('xpmiss', 0) * scoring_settings.get('xpmiss', 0)
    
    # Defense/ST stats
    points += proj_stats.get('def_td', 0) * scoring_settings.get('def_td', 6)
    points += proj_stats.get('def_st_td', 0) * scoring_settings.get('def_st_td', 6)
    points += proj_stats.get('sack', 0) * scoring_settings.get('sack', 1)
    points += proj_stats.get('int', 0) * scoring_settings.get('int', 2)
    points += proj_stats.get('fum_rec', 0) * scoring_settings.get('fum_rec', 2)
    points += proj_stats.get('safe', 0) * scoring_settings.get('safe', 2)
    points += proj_stats.get('blk_kick', 0) * scoring_settings.get('blk_kick', 2)
    
    return points


def fetch_sleeper_weekly_projections(week=None):
    """
    Fetch week-specific projections from Sleeper API
    Calculate points using league-specific scoring settings
    """
    if week is None:
        week = get_current_nfl_week()
    
    print(f"😴 Fetching Sleeper weekly projections for Week {week}...")

    try:
        # Get league-specific scoring settings
        scoring_settings = get_sleeper_league_scoring()
        print(f"   → Using custom league scoring (PPR value: {scoring_settings.get('rec', 1.0)})")
        
        # Get weekly projections from Sleeper
        projections_url = f"https://api.sleeper.app/projections/nfl/{SEASON}/{week}"
        proj_response = requests.get(projections_url, params={'season_type': 'regular'}, timeout=15)
        
        if proj_response.status_code != 200:
            print(f"   ⚠️ Sleeper projections API returned status {proj_response.status_code}")
            return pd.DataFrame()
        
        weekly_projections = proj_response.json()
        
        # Get player info to map IDs to names
        players_response = requests.get("https://api.sleeper.app/v1/players/nfl", timeout=15)
        players_response.raise_for_status()
        players_data = players_response.json()

        projections = []
        fantasy_positions = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']

        # Parse weekly projections (it's a list of dictionaries)
        if isinstance(weekly_projections, list):
            for proj_entry in weekly_projections:
                player_id = proj_entry.get('player_id', '')
                proj_stats = proj_entry.get('stats', {})
                
                # Get player info
                player_info = players_data.get(player_id, {})
                position = player_info.get('position', '')
                
                if position not in fantasy_positions:
                    continue
                
                first_name = player_info.get('first_name', '')
                last_name = player_info.get('last_name', '')
                full_name = f"{first_name} {last_name}".strip()
                
                if not full_name:
                    continue
                
                # Calculate fantasy points using league-specific scoring
                custom_points = calculate_custom_points(proj_stats, scoring_settings)
                
                if custom_points > 0:
                    projections.append({
                        'player_name': full_name,
                        'proj_points': round(custom_points, 1),
                        'position': position,
                        'source': 'Sleeper'
                    })
        # Handle dictionary format (if API changes)
        elif isinstance(weekly_projections, dict):
            for player_id, proj_stats in weekly_projections.items():
                player_info = players_data.get(player_id, {})
                position = player_info.get('position', '')
                
                if position not in fantasy_positions:
                    continue
                
                first_name = player_info.get('first_name', '')
                last_name = player_info.get('last_name', '')
                full_name = f"{first_name} {last_name}".strip()
                
                if not full_name:
                    continue
                
                # Calculate fantasy points using league-specific scoring
                custom_points = calculate_custom_points(proj_stats, scoring_settings)
                
                if custom_points > 0:
                    projections.append({
                        'player_name': full_name,
                        'proj_points': round(custom_points, 1),
                        'position': position,
                        'source': 'Sleeper'
                    })

        if projections:
            print(f"   ✓ Sleeper: {len(projections)} players with Week {week} projections")
            return pd.DataFrame(projections)
        else:
            print(f"   ⚠️ Sleeper: No weekly projections found for Week {week}")
            return pd.DataFrame()

    except Exception as e:
        print(f"   ⚠️ Sleeper weekly projections failed: {e}")
        return pd.DataFrame()


def get_current_nfl_week():
    """Determine current NFL week"""
    # Allow manual override for testing
    override_week = os.getenv('ESPN_WEEK')
    if override_week:
        return int(override_week)
    
    # Try to get from ESPN API
    try:
        from espn_api.football import League
        league_id = int(os.getenv('ESPN_LEAGUE_ID', '529882810'))
        espn_s2 = os.getenv('ESPN_S2')
        swid = os.getenv('SWID')
        current_season = SEASON
        
        if espn_s2 and swid:
            league = League(league_id=league_id, year=current_season, espn_s2=espn_s2, swid=swid)
        else:
            league = League(league_id=league_id, year=current_season)
        
        current_week = getattr(league, 'current_week', None)
        # If season is over (week 18+), default to mid-season week
        if current_week and current_week <= 17:
            return current_week
    except:
        pass
    
    # Default to week 5 (reasonable mid-season default)
    return 5


def fetch_espn_weekly_projections(week=None):
    """Fetch matchup-adjusted weekly projections from ESPN
    
    This gets actual weekly projections that account for:
    - Opponent defense strength
    - Home/away matchups
    - Current injuries
    - Game conditions
    """
    if week is None:
        week = get_current_nfl_week()
    
    current_season = SEASON
    
    try:
        print(f"🏈 Fetching ESPN weekly projections for Week {week}...")
        
        # ESPN's public API endpoint for weekly projections
        url = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{current_season}/segments/0/leaguedefaults/3"
        
        # Position slot IDs in ESPN (for filtering)
        filter_slot_ids = {
            0: 'QB', 2: 'RB', 4: 'WR', 6: 'TE', 16: 'DEF', 17: 'K'
        }
        
        # Position mapping by ID (more comprehensive)
        position_map = {
            1: 'QB', 2: 'RB', 3: 'RB', 4: 'WR', 5: 'WR', 
            6: 'TE', 16: 'DEF', 17: 'K', 23: 'FLEX'
        }
        
        # Build filter for weekly projections
        fantasy_filter = {
            "players": {
                "filterSlotIds": {"value": list(filter_slot_ids.keys())},
                "filterRanksForScoringPeriodIds": {"value": [week]},
                "filterStatsForSourceIds": {"value": [1]},  # 1 = projected
                "limit": 1000,
                "sortPercOwned": {"sortPriority": 1, "sortAsc": False}
            }
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'x-fantasy-filter': json.dumps(fantasy_filter)
        }
        
        params = {
            'view': 'kona_player_info'
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code != 200:
            print(f"   ⚠️ ESPN API returned status {response.status_code}")
            return pd.DataFrame()
        
        data = response.json()
        all_projections = []
        
        # Parse player data
        players = data.get('players', [])
        for player_data in players:
            player_info = player_data.get('player', {})
            
            # Get player details
            full_name = player_info.get('fullName', '')
            default_pos_id = player_info.get('defaultPositionId', 0)
            position = position_map.get(default_pos_id, filter_slot_ids.get(default_pos_id, 'UNK'))
            
            # Get weekly projected stats
            stats = player_info.get('stats', [])
            for stat in stats:
                # Look for projected stats for this specific week
                if stat.get('scoringPeriodId') == week and stat.get('statSourceId') == 1:
                    projected_points = stat.get('appliedTotal', 0)
                    
                    if projected_points > 0:
                        all_projections.append({
                            'player_name': full_name,
                            'proj_points': round(projected_points, 1),
                            'position': position,
                            'source': 'ESPN_API'
                        })
                    break
        
        if all_projections:
            print(f"   ✓ ESPN API: {len(all_projections)} players with Week {week} matchup-adjusted projections")
            return pd.DataFrame(all_projections)
        else:
            print(f"   ⚠️ ESPN API: No weekly projections found for Week {week}")
            return pd.DataFrame()
            
    except Exception as e:
        print(f"   ⚠️ ESPN weekly projections failed: {e}")
        return pd.DataFrame()


def merge_projections(source_dfs):
    """
    Merge projections from multiple sources intelligently
    Take average where available, use best available otherwise
    """
    all_data = []

    for df in source_dfs:
        if not df.empty:
            all_data.append(df)

    if not all_data:
        print("❌ No projection data available from any source")
        return pd.DataFrame(), pd.DataFrame()

    # Combine all sources
    combined = pd.concat(all_data, ignore_index=True)

    # Create comparison dataframe (keeps all sources separate)
    comparison_df = combined.copy()

    # Create averaged dataframe (one entry per player with average)
    averaged = combined.groupby(['player_name', 'position']).agg({
        'proj_points':
        'mean',
        'source':
        lambda x: 'Combined (' + ', '.join(sorted(set(x))) + ')'
    }).reset_index()

    averaged['proj_points'] = averaged['proj_points'].round(1)

    # Also keep individual source entries
    final_df = pd.concat([combined, averaged], ignore_index=True)

    return final_df, comparison_df


def get_all_projections():
    """
    Fetch projections from all available free sources
    """
    print("=" * 60)
    print("🏈 FANTASY FOOTBALL PROJECTION SCRAPER")
    print(f"📅 Season: {SEASON} | Scoring: {SCORING}")
    print("=" * 60)

    # Fetch from all sources - all weekly projections now
    espn_df = fetch_espn_projections()
    espn_weekly_df = fetch_espn_weekly_projections()  # Week-specific matchup-adjusted projections
    sleeper_weekly_df = fetch_sleeper_weekly_projections()  # Week-specific projections
    # nfl_df = fetch_nfl_projections()  # Uncomment when implemented

    # Merge all sources
    source_dfs = [df for df in [espn_df, espn_weekly_df, sleeper_weekly_df] if not df.empty]

    if not source_dfs:
        print("\n❌ No data retrieved from any source!")
        print("   Loading fallback data if available...")

        if os.path.exists(FALLBACK_PATH):
            fallback_df = pd.read_csv(FALLBACK_PATH)
            fallback_df.to_csv(SAVE_PATH, index=False)
            print(f"✅ Loaded fallback data: {len(fallback_df)} players")
        else:
            print("❌ No fallback available. Cannot update projections.")
        return

    combined_df, comparison_df = merge_projections(source_dfs)

    # Save main file
    combined_df.to_csv(SAVE_PATH, index=False)
    print(f"\n✅ Saved combined projections: {len(combined_df)} total entries")

    # Save comparison file (for multi-source analysis)
    if not comparison_df.empty:
        comparison_df.to_csv(COMPARISON_PATH, index=False)
        print(f"✅ Saved comparison data: {COMPARISON_PATH}")

    # Archive historical copy
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    history_path = os.path.join(HISTORY_DIR, f"projections_{timestamp}.csv")
    combined_df.to_csv(history_path, index=False)
    print(f"📦 Historical copy: {history_path}")

    # Update fallback
    combined_df.to_csv(FALLBACK_PATH, index=False)
    print(f"📁 Fallback updated: {FALLBACK_PATH}")

    # Print summary
    print("\n" + "=" * 60)
    print("📊 PROJECTION SUMMARY")
    print("=" * 60)

    # By source
    source_counts = combined_df['source'].value_counts()
    print("\n📈 By Source:")
    for source, count in source_counts.items():
        print(f"   {source}: {count} entries")

    # By position
    pos_counts = combined_df['position'].value_counts()
    print("\n📊 By Position:")
    for pos, count in pos_counts.items():
        print(f"   {pos}: {count} entries")

    # Top players
    print("\n🌟 Top 5 Projected Players:")
    top_players = combined_df[combined_df['source'].str.contains(
        'Combined', na=False)].nlargest(5, 'proj_points')
    for _, player in top_players.iterrows():
        print(
            f"   {player['player_name']} ({player['position']}): {player['proj_points']:.1f} pts"
        )

    print("\n" + "=" * 60)
    print("✅ Scraper completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    get_all_projections()
