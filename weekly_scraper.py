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
# Updated to use the FantasyPros PPR rankings pages
BASE_URL_TPL = "https://www.fantasypros.com/nfl/rankings/ppr-{position}.php"

SAVE_PATH     = "projections.csv"
FALLBACK_PATH = "projections_fallback.csv"
HISTORY_DIR   = "history"

# Ensure history directory exists
os.makedirs(HISTORY_DIR, exist_ok=True)


def fetch_fp_rankings_html(position: str) -> pd.DataFrame:
    """
    Scrape the FantasyPros HTML rankings table for a given position and
    return a DataFrame with columns: player_name, proj_points, position.
    """
    url = BASE_URL_TPL.format(position=position)
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


def get_all_projections():
    """
    Fetch projections for all positions, save the combined CSV,
    archive a dated copy, and update the fallback.
    """
    dfs = []
    for pos in POSITIONS:
        df = fetch_fp_rankings_html(pos)
        if df.empty:
            print(f"⚠️ No data for {pos.upper()}.")
        else:
            dfs.append(df)

    # If no data was fetched, load fallback
    if not dfs:
        print("⚠️ All positions returned empty. Loading fallback data.")
        if os.path.exists(FALLBACK_PATH):
            fallback_df = pd.read_csv(FALLBACK_PATH)
            fallback_df.to_csv(SAVE_PATH, index=False)
            print(f"✅ Fallback data loaded from {FALLBACK_PATH}")
        else:
            print("❌ No fallback available. No projections updated.")
        return

    # Combine and save
    full_df = pd.concat(dfs, ignore_index=True)
    full_df.to_csv(SAVE_PATH, index=False)

    # Archive historical copy
    timestamp = datetime.now().strftime("%Y-%m-%d")
    history_path = os.path.join(HISTORY_DIR, f"projections_{timestamp}.csv")
    full_df.to_csv(history_path, index=False)

    # Update fallback
    full_df.to_csv(FALLBACK_PATH, index=False)

    print(f"✅ Saved projections to {SAVE_PATH} ({len(full_df)} players).")
    print(f"📦 Historical copy saved to {history_path}")
    print(f"📁 Fallback updated at {FALLBACK_PATH}")


if __name__ == "__main__":
    get_all_projections()
