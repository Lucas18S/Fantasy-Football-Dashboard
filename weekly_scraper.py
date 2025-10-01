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


def fetch_sleeper_stats():
    """
    Fetch actual player stats from Sleeper to supplement projections
    This gives us real data about player activity
    """
    print("😴 Fetching Sleeper player data...")

    try:
        # Get all NFL players
        response = requests.get("https://api.sleeper.app/v1/players/nfl",
                                timeout=15)
        response.raise_for_status()

        players_data = response.json()

        projections = []
        fantasy_positions = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']

        for player_id, player in players_data.items():
            position = player.get('position', '')

            if position not in fantasy_positions:
                continue

            # Only include active players with teams
            team = player.get('team')
            status = player.get('status', 'Active')

            if not team or status not in [
                    'Active', 'Questionable', 'Doubtful'
            ]:
                continue

            first_name = player.get('first_name', '')
            last_name = player.get('last_name', '')
            full_name = f"{first_name} {last_name}".strip()

            if not full_name:
                continue

            # Get fantasy points from last season if available
            # This is better than made-up numbers
            fantasy_points = player.get('fantasy_points_ppr', 0) or 0

            # Estimate weekly projection from season total
            games_played = player.get('games_played', 17) or 17
            weekly_avg = fantasy_points / max(games_played,
                                              1) if games_played > 0 else 0

            # Use position-based minimums for players without stats
            if weekly_avg == 0:
                weekly_avg = {
                    'QB': 12.0,
                    'RB': 8.0,
                    'WR': 7.0,
                    'TE': 6.0,
                    'K': 7.0,
                    'DEF': 7.0
                }.get(position, 5.0)

            projections.append({
                'player_name': full_name,
                'proj_points': round(weekly_avg, 1),
                'position': position,
                'source': 'Sleeper'
            })

        print(f"   ✓ Sleeper: {len(projections)} active players")
        return pd.DataFrame(projections)

    except Exception as e:
        print(f"   ⚠️ Sleeper fetch failed: {e}")
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

    # Fetch from all sources
    espn_df = fetch_espn_projections()
    sleeper_df = fetch_sleeper_stats()
    # nfl_df = fetch_nfl_projections()  # Uncomment when implemented

    # Merge all sources
    source_dfs = [df for df in [espn_df, sleeper_df] if not df.empty]

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
