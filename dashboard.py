import streamlit as st
import requests
import pandas as pd
import os
import time
from datetime import datetime
from pandas.errors import EmptyDataError

# ─── Config ───────────────────────────────────────────────────────────────────
LEAGUE_ID       = '1185263580356419584'
PROJ_FILE       = "projections.csv"
FALLBACK_FILE   = "projections_fallback.csv"
FRESHNESS_HOURS = 24

# ─── Data Loading ──────────────────────────────────────────────────────────────
@st.cache_data
def get_data():
    try:
        users   = requests.get(f'https://api.sleeper.app/v1/league/{LEAGUE_ID}/users').json()
        rosters = requests.get(f'https://api.sleeper.app/v1/league/{LEAGUE_ID}/rosters').json()
        players = requests.get('https://api.sleeper.app/v1/players/nfl').json()
        return users, rosters, players
    except Exception as e:
        st.error(f"Data load error: {e}")
        return [], [], {}

@st.cache_data
def load_projections():
    try:
        df = pd.read_csv(PROJ_FILE)
    except (FileNotFoundError, EmptyDataError):
        st.warning("⚠️ Live projections unavailable. Using fallback data.")
        try:
            df = pd.read_csv(FALLBACK_FILE)
        except (FileNotFoundError, EmptyDataError):
            st.error("❌ No projection data available. Please run the scraper.")
            return pd.DataFrame(columns=["player_name","proj_points","position"])
    df['player_name'] = df['player_name'].str.strip()
    df['position']    = df['position'].str.upper()
    df['proj_points'] = pd.to_numeric(df['proj_points'], errors='coerce')
    return df.dropna()

def is_file_stale(path, max_age_hours=FRESHNESS_HOURS):
    if not os.path.exists(path):
        return True
    return (time.time() - os.path.getmtime(path)) > (max_age_hours * 3600)

# ─── Helpers ───────────────────────────────────────────────────────────────────
def get_player_name(pid, players):
    return players.get(pid, {}).get('full_name', 'Unknown')

def get_player_position(pid, players):
    return players.get(pid, {}).get('position', 'UNK')

def get_projection(name, proj_df):
    row = proj_df[proj_df['player_name'].str.lower() == name.lower()]
    return float(row['proj_points'].values[0]) if not row.empty else 0.0

def build_optimal_lineup(player_ids, players, proj_df):
    entries = []
    for pid in player_ids:
        name  = get_player_name(pid, players)
        pos   = get_player_position(pid, players)
        pts   = get_projection(name, proj_df)
        entries.append({'id': pid, 'name': name, 'pos': pos, 'points': pts})
    df = pd.DataFrame(entries).sort_values('points', ascending=False)

    lineup = {'QB': [], 'RB': [], 'WR': [], 'TE': [], 'FLEX': [], 'SUPERFLEX': [], 'K': [], 'DEF': []}
    used = set()
    def assign(slot, position, limit):
        c = 0
        for _, r in df[df['pos'] == position].iterrows():
            if r['id'] not in used and c < limit:
                lineup[slot].append(r)
                used.add(r['id'])
                c += 1

    assign('QB',       'QB',  1)
    assign('RB',       'RB',  2)
    assign('WR',       'WR',  3)
    assign('TE',       'TE',  1)
    assign('K',        'K',   1)
    assign('DEF',      'DEF', 1)

    # One FLEX (RB/WR/TE)
    for _, r in df[df['pos'].isin(['RB','WR','TE'])].iterrows():
        if r['id'] not in used:
            lineup['FLEX'].append(r)
            used.add(r['id'])
            break
    # One SUPERFLEX (any non-K/DEF)
    for _, r in df[~df['pos'].isin(['K','DEF'])].iterrows():
        if r['id'] not in used:
            lineup['SUPERFLEX'].append(r)
            used.add(r['id'])
            break

    return lineup

def get_bench_recommendations(player_ids, players, proj_df, optimal):
    all_ids     = set(player_ids)
    optimal_ids = {p['id'] for slot in optimal.values() for p in slot}
    bench_ids   = all_ids - optimal_ids

    recs = []
    for pid in bench_ids:
        name = get_player_name(pid, players)
        pos  = get_player_position(pid, players)
        pts  = get_projection(name, proj_df)
        recs.append({'name': name, 'pos': pos, 'points': pts})

    return pd.DataFrame(recs).sort_values('points', ascending=False)

# ─── Streamlit App ────────────────────────────────────────────────────────────
st.set_page_config(page_title="Fantasy Dashboard", layout="wide")
st.title("🏈 Fantasy Start/Sit Dashboard")

# Health check
if is_file_stale(PROJ_FILE):
    st.warning("⚠️ Projections data is over 24 hours old — accuracy may suffer.")

users, rosters, players = get_data()
projections = load_projections()

# Team selector
manager_names   = {r['owner_id']: next((u['display_name'] for u in users if u['user_id']==r['owner_id']), 'Unknown') for r in rosters}
selected_manager= st.selectbox("Select a team:", list(manager_names.values()))
selected_roster = next(r for r in rosters if manager_names[r['owner_id']]==selected_manager)
player_ids      = selected_roster.get('players', [])
starters_ids    = selected_roster.get('starters', [])

# Start/Sit Advice
st.markdown("---")
st.markdown(f"### 🔍 Start/Sit Advice for {selected_manager}")
optimal = build_optimal_lineup(player_ids, players, projections)
total   = 0
for slot, plist in optimal.items():
    st.markdown(f"**{slot}:**")
    for p in plist:
        st.write(f"- {p['name']} — **{p['points']:.1f} pts**")
        total += p['points']
st.success(f"✅ Optimal Projected Total: **{total:.1f} pts**")

# Bad starts
st.markdown("---")
bad = [pid for pid in starters_ids if pid not in {p['id'] for slot in optimal.values() for p in slot}]
if bad:
    st.warning("⚠️ Consider benching:")
    for pid in bad:
        st.write(f"- {get_player_name(pid, players)}")
else:
    st.info("✅ All your current starters are optimal!")

# Bench Recommendations
st.markdown("---")
st.markdown("### 🪑 Bench Recommendations")
bench_df = get_bench_recommendations(player_ids, players, projections, optimal)
if bench_df.empty:
    st.write("No bench players found.")
else:
    for _, row in bench_df.iterrows():
        st.write(f"- {row['name']} ({row['pos']}) — **{row['points']:.1f} pts**")
