import pandas as pd
import os
from datetime import datetime

# ─── Configuration ─────────────────────────────────────────────────────────────
SEASON        = 2025
SCORING       = "PPR"
POSITIONS     = ["qb", "rb", "wr", "te"]
BASE_URL_TPL  = (
    "https://www.fantasypros.com/nfl/rankings/{position}.php"
    "?export=csv&season={season}&scoring={scoring}"
)

SAVE_PATH     = "projections.csv"
FALLBACK_PATH = "projections_fallback.csv"
HISTORY_DIR   = "history"

# Ensure history directory exists
os.makedirs(HISTORY_DIR, exist_ok=True)


def fetch_fp_rankings_csv(position: str) -> pd.DataFrame:
    """
    Fetch the FantasyPros CSV export for a given position and
    return a DataFrame with columns: player_name, proj_points, position.
    """
    url = BASE_URL_TPL.format(position=position, season=SEASON, scoring=SCORING)
    try:
        df = pd.read_csv(url)
    except Exception as e:
        print(f"⚠️ Failed to fetch {position.upper()} CSV: {e}")
        return pd.DataFrame()

    # Check for required columns
    if "Player" not in df.columns:
        print(f"⚠️ 'Player' column not found for {position.upper()}")
        return pd.DataFrame()
    # Find the fantasy points column (exact "FPTS" or any column containing "FPTS")
    fpts_col = next((c for c in df.columns if c.upper() == "FPTS"), None)
    if fpts_col is None:
        fpts_col = next((c for c in df.columns if "FPTS" in c.upper()), None)
    if fpts_col is None:
        print(f"⚠️ Fantasy points column not found for {position.upper()}")
        return pd.DataFrame()

    # Normalize columns
    df = df.rename(columns={"Player": "player_name", fpts_col: "proj_points"})
    df["position"] = position.upper()

    # Keep only the needed fields
    df = df[["player_name", "proj_points", "position"]].copy()
    # Clean and ensure numeric projections
    df["player_name"] = df["player_name"].str.strip()
    df["proj_points"] = pd.to_numeric(df["proj_points"], errors="coerce")
    return df.dropna()


def get_all_projections():
    """
    Fetch projections for all positions, save the combined CSV,
    archive a dated copy, and update the fallback.
    """
    dfs = []
    for pos in POSITIONS:
        df = fetch_fp_rankings_csv(pos)
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
