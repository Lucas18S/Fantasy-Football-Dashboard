import pandas as pd

def get_weekly_projections():
    df = pd.read_csv("projections.csv")
    df['proj_points'] = pd.to_numeric(df['proj_points'], errors='coerce')
    df.dropna(subset=['player_name', 'proj_points', 'position'], inplace=True)
    df['player_name'] = df['player_name'].str.strip()
    df['position'] = df['position'].str.upper()
    return df

if __name__ == "__main__":
    df = get_weekly_projections()
    print("\n📊 Top Fantasy Projections (CSV-based):\n")
    print(df.head(20).to_string(index=False))
