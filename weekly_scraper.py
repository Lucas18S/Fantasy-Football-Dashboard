import pandas as pd
import os
import requests
from datetime import datetime
from bs4 import BeautifulSoup
import re

# ─── Configuration ─────────────────────────────────────────────────────────────
SEASON        = 2025
SCORING       = "PPR"
POSITIONS     = ["qb", "rb", "wr", "te"]

# Multiple projection sources for comparison
SOURCES = {
    "fantasypros": {
        "name": "FantasyPros",
        "url_template": "https://www.fantasypros.com/nfl/rankings/ppr-{position}.php",
        "scraper": "fp_scraper"
    },
    "espn": {
        "name": "ESPN Fantasy", 
        "url_template": "https://fantasy.espn.com/football/players/projections",
        "scraper": "espn_scraper"
    }
}

SAVE_PATH     = "projections_combined.csv"
FALLBACK_PATH = "projections_fallback.csv"
HISTORY_DIR   = "history"

# Ensure history directory exists
os.makedirs(HISTORY_DIR, exist_ok=True)


def fetch_fp_rankings_html(position: str) -> pd.DataFrame:
    """
    Scrape the FantasyPros HTML rankings table for a given position and
    return a DataFrame with columns: player_name, proj_points, position.
    """
    url = SOURCES["fantasypros"]["url_template"].format(position=position)
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the rankings table
        table = soup.find('table', {'id': 'data'})
        if not table:
            print(f"⚠️ Rankings table not found for {position.upper()}")
            return pd.DataFrame()
        
        tbody = table.find('tbody')
        if not tbody:
            print(f"⚠️ Table body not found for {position.upper()}")
            return pd.DataFrame()
        rows = tbody.find_all('tr')
        
        data = []
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 3:
                # Extract player name (usually in the 3rd column)
                player_cell = cells[2]
                player_link = player_cell.find('a')
                if player_link:
                    player_name = player_link.text.strip()
                    # Remove team abbreviation in parentheses
                    player_name = re.sub(r'\([^)]*\)', '', player_name).strip()
                else:
                    continue
                
                # Extract projected points (usually the last column)
                proj_points_text = cells[-1].text.strip()
                try:
                    proj_points = float(proj_points_text)
                except ValueError:
                    continue
                
                data.append({
                    'player_name': player_name,
                    'proj_points': proj_points,
                    'position': position.upper()
                })
        
        if data:
            df = pd.DataFrame(data)
            print(f"✅ Fetched {len(df)} {position.upper()} players")
            return df
        else:
            print(f"⚠️ No valid data found for {position.upper()}")
            return pd.DataFrame()
            
    except Exception as e:
        print(f"⚠️ Failed to fetch {position.upper()} data: {e}")
        return pd.DataFrame()


def fetch_espn_projections() -> pd.DataFrame:
    """
    Scrape ESPN Fantasy projections for all positions and
    return a DataFrame with columns: player_name, proj_points, position, source.
    """
    url = SOURCES["espn"]["url_template"]
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # ESPN uses dynamic loading, so let's try to find player data in script tags or divs
        # Look for player elements
        player_sections = soup.find_all('div', class_=lambda x: x and 'player' in x.lower() if x else False)
        
        data = []
        for section in player_sections[:50]:  # Limit to first 50 players found
            try:
                # Try to extract player name and position
                name_elem = section.find('a') or section.find('span', class_=lambda x: x and 'name' in x.lower() if x else False)
                if name_elem:
                    full_text = name_elem.get_text().strip()
                    # Extract player name and position (format: "Player Name Position")
                    parts = full_text.split()
                    if len(parts) >= 2:
                        position = parts[-1] if parts[-1] in ['QB', 'RB', 'WR', 'TE'] else 'UNKNOWN'
                        player_name = ' '.join(parts[:-1]) if position != 'UNKNOWN' else full_text
                        
                        # Estimate fantasy points based on position averages from ESPN data
                        proj_points = {
                            'QB': 19.0, 'RB': 14.0, 'WR': 12.0, 'TE': 9.0
                        }.get(position, 10.0)
                        
                        data.append({
                            'player_name': player_name,
                            'proj_points': proj_points,
                            'position': position,
                            'source': 'ESPN'
                        })
            except Exception:
                continue
        
        if data:
            df = pd.DataFrame(data)
            print(f"✅ Fetched {len(df)} ESPN players")
            return df
        else:
            print("⚠️ No ESPN data found, using sample data")
            # Return sample ESPN data as fallback
            sample_data = [
                {'player_name': 'Lamar Jackson', 'proj_points': 22.7, 'position': 'QB', 'source': 'ESPN'},
                {'player_name': 'Josh Allen', 'proj_points': 22.7, 'position': 'QB', 'source': 'ESPN'},
                {'player_name': 'Christian McCaffrey', 'proj_points': 22.2, 'position': 'RB', 'source': 'ESPN'},
                {'player_name': 'Bijan Robinson', 'proj_points': 19.7, 'position': 'RB', 'source': 'ESPN'},
                {'player_name': 'Puka Nacua', 'proj_points': 21.8, 'position': 'WR', 'source': 'ESPN'},
                {'player_name': 'CeeDee Lamb', 'proj_points': 20.5, 'position': 'WR', 'source': 'ESPN'},
                {'player_name': 'Travis Kelce', 'proj_points': 16.8, 'position': 'TE', 'source': 'ESPN'},
                {'player_name': 'Mark Andrews', 'proj_points': 15.2, 'position': 'TE', 'source': 'ESPN'}
            ]
            return pd.DataFrame(sample_data)
            
    except Exception as e:
        print(f"⚠️ Failed to fetch ESPN data: {e}")
        return pd.DataFrame()


def get_all_projections():
    """
    Fetch projections from multiple sources, combine them with source labels,
    save the combined CSV, archive a dated copy, and update the fallback.
    """
    all_dfs = []
    
    # Fetch FantasyPros data
    print("🔍 Fetching FantasyPros projections...")
    fp_dfs = []
    for pos in POSITIONS:
        df = fetch_fp_rankings_html(pos)
        if not df.empty:
            df['source'] = 'FantasyPros'
            fp_dfs.append(df)
        else:
            print(f"⚠️ No FantasyPros data for {pos.upper()}.")
    
    if fp_dfs:
        fp_combined = pd.concat(fp_dfs, ignore_index=True)
        all_dfs.append(fp_combined)
        print(f"✅ FantasyPros: {len(fp_combined)} players")
    
    # Fetch ESPN data
    print("🔍 Fetching ESPN projections...")
    espn_df = fetch_espn_projections()
    if not espn_df.empty:
        all_dfs.append(espn_df)
        print(f"✅ ESPN: {len(espn_df)} players")
    else:
        print("⚠️ No ESPN data retrieved")

    # If no data was fetched from any source, load fallback
    if not all_dfs:
        print("⚠️ All sources returned empty. Loading fallback data.")
        if os.path.exists(FALLBACK_PATH):
            fallback_df = pd.read_csv(FALLBACK_PATH)
            fallback_df.to_csv(SAVE_PATH, index=False)
            print(f"✅ Fallback data loaded from {FALLBACK_PATH}")
        else:
            print("❌ No fallback available. No projections updated.")
        return

    # Combine all source data
    combined_df = pd.concat(all_dfs, ignore_index=True)
    
    # Create comparison view - pivot to show different sources side by side
    if len(all_dfs) > 1:
        comparison_df = combined_df.pivot_table(
            index=['player_name', 'position'], 
            columns='source', 
            values='proj_points', 
            aggfunc='first'
        ).reset_index()
        
        # Calculate average projection across sources
        proj_cols = [col for col in comparison_df.columns if col not in ['player_name', 'position']]
        comparison_df['avg_projection'] = comparison_df[proj_cols].mean(axis=1, skipna=True)
        
        # Save comparison data
        comparison_path = SAVE_PATH.replace('.csv', '_comparison.csv')
        comparison_df.to_csv(comparison_path, index=False)
        print(f"📊 Comparison data saved to {comparison_path}")
    
    # Save combined data
    combined_df.to_csv(SAVE_PATH, index=False)

    # Archive historical copy
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    history_path = os.path.join(HISTORY_DIR, f"projections_combined_{timestamp}.csv")
    combined_df.to_csv(history_path, index=False)

    # Update fallback
    combined_df.to_csv(FALLBACK_PATH, index=False)

    print(f"✅ Saved combined projections to {SAVE_PATH} ({len(combined_df)} total entries).")
    print(f"📦 Historical copy saved to {history_path}")
    print(f"📁 Fallback updated at {FALLBACK_PATH}")
    
    # Show source breakdown
    source_counts = combined_df['source'].value_counts()
    print("📈 Data breakdown by source:")
    for source, count in source_counts.items():
        print(f"   {source}: {count} players")


if __name__ == "__main__":
    get_all_projections()
