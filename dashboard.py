import streamlit as st
import requests
import pandas as pd
import os
import time
from datetime import datetime
from pandas.errors import EmptyDataError

# ─── Config ───────────────────────────────────────────────────────────────────
LEAGUE_ID       = '1185263580356419584'
PROJ_FILE       = "projections_combined.csv"
COMPARISON_FILE = "projections_combined_comparison.csv"
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
            return pd.DataFrame({"player_name": [], "proj_points": [], "position": [], "source": []})
    df['player_name'] = df['player_name'].str.strip()
    df['position']    = df['position'].str.upper()
    df['proj_points'] = pd.to_numeric(df['proj_points'], errors='coerce')
    # Add source column if it doesn't exist (for backward compatibility)
    if 'source' not in df.columns:
        df['source'] = 'FantasyPros'
    return df.dropna()

@st.cache_data  
def load_comparison_data():
    """Load side-by-side comparison data from multiple sources"""
    try:
        df = pd.read_csv(COMPARISON_FILE)
        return df
    except (FileNotFoundError, EmptyDataError):
        return pd.DataFrame()

def is_file_stale(path, max_age_hours=FRESHNESS_HOURS):
    if not os.path.exists(path):
        return True
    return (time.time() - os.path.getmtime(path)) > (max_age_hours * 3600)

# ─── Helpers ───────────────────────────────────────────────────────────────────
def get_player_name(pid, players):
    return players.get(pid, {}).get('full_name', 'Unknown')

def get_player_position(pid, players):
    return players.get(pid, {}).get('position', 'UNK')

def estimate_projection_by_position(player_name):
    """Provide reasonable fallback projections for players not in our dataset"""
    # This prevents players from showing as 0.0 points
    # Could be enhanced to use player names to guess position
    return 8.0  # Conservative baseline for any fantasy-relevant player

def get_projection(name, proj_df, source=None):
    """Get projection for a player, optionally filtered by source"""
    mask = proj_df['player_name'].str.lower() == name.lower()
    if source:
        mask = mask & (proj_df['source'] == source)
    row = proj_df[mask]
    if not row.empty:
        return float(row['proj_points'].values[0])
    else:
        # If no projection found, return a reasonable position-based estimate
        # This prevents players from showing as 0.0 points
        return estimate_projection_by_position(name)

def get_projection_comparison(name, proj_df):
    """Get all projections for a player from different sources"""
    player_rows = proj_df[proj_df['player_name'].str.lower() == name.lower()]
    if player_rows.empty:
        return {}
    
    comparison = {}
    for _, row in player_rows.iterrows():
        source = row.get('source', 'Unknown')
        comparison[source] = float(row['proj_points'])
    return comparison

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
comparison_data = load_comparison_data()

# Show data source info
if 'source' in projections.columns:
    sources = projections['source'].unique()
    source_counts = projections['source'].value_counts()
    st.info(f"📊 **Projection Sources**: {', '.join(sources)} | Total Players: {len(projections)}")
    
    # Show breakdown by source  
    if len(sources) > 1:
        cols = st.columns(len(sources))
        for i, source in enumerate(sources):
            with cols[i]:
                count = source_counts[source]
                st.metric(f"{source}", f"{count} players")

        # Add projection comparison view
        st.markdown("### 📊 Projection Source Comparison")
        
        # Top players comparison (only show if multiple sources)
        if len(sources) > 1:
            with st.expander("🔥 Top Players - Multi-Source Comparison", expanded=False):
                top_players = projections.groupby('player_name')['proj_points'].mean().nlargest(10).index
                
                for player in top_players:
                    player_comparisons = get_projection_comparison(player, projections)
                    if len(player_comparisons) > 1:
                        st.write(f"**{player}:**")
                        comp_cols = st.columns(len(player_comparisons) + 1)
                        
                        sources_list = list(player_comparisons.keys())
                        points_list = list(player_comparisons.values())
                        avg_points = sum(points_list) / len(points_list)
                        
                        for i, (source, points) in enumerate(player_comparisons.items()):
                            with comp_cols[i]:
                                st.metric(source, f"{points:.1f} pts")
                        
                        with comp_cols[-1]:
                            st.metric("Average", f"{avg_points:.1f} pts", delta=f"{max(points_list) - min(points_list):.1f} spread")

# Source selector
if 'source' in projections.columns:
    available_sources = ['Best Available (Combined)'] + list(projections['source'].unique())
    selected_source = st.selectbox("Choose projection source:", available_sources)
    
    # Filter projections based on selected source
    if selected_source == 'Best Available (Combined)':
        working_projections = projections
        st.info(f"🎯 Using **combined projections** from all sources")
    else:
        working_projections = projections[projections['source'] == selected_source]
        st.info(f"🎯 Using **{selected_source}** projections only ({len(working_projections)} players)")
else:
    working_projections = projections
    st.info("📊 Using available projection data")

# Team selector
manager_names   = {r['owner_id']: next((u['display_name'] for u in users if u['user_id']==r['owner_id']), 'Unknown') for r in rosters}
selected_manager= st.selectbox("Select a team:", list(manager_names.values()))
selected_roster = next(r for r in rosters if manager_names[r['owner_id']]==selected_manager)
player_ids      = selected_roster.get('players', [])
starters_ids    = selected_roster.get('starters', [])

# Start/Sit Advice
st.markdown("---")
source_display = selected_source if 'source' in projections.columns and 'selected_source' in locals() else "Sleeper"
st.markdown(f"### 🔍 Start/Sit Advice for {selected_manager}")
st.caption(f"Based on {source_display} projections")
optimal = build_optimal_lineup(player_ids, players, working_projections)
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

# Complete Roster Analysis
st.markdown("---")
st.markdown("### 📋 Complete Roster Analysis")
st.caption(f"All your players with projections - Based on {source_display}")

# Get all roster players with projections
all_roster_players = []
for pid in player_ids:
    name = get_player_name(pid, players)
    pos = get_player_position(pid, players)
    proj_points = get_projection(name, working_projections)
    is_starter = pid in starters_ids
    is_optimal = pid in {p['id'] for slot in optimal.values() for p in slot}
    
    # Determine recommendation
    if is_optimal:
        recommendation = "✅ START"
        reason = "In optimal lineup"
        priority = 1
    elif is_starter and not is_optimal:
        recommendation = "⚠️ CONSIDER BENCH"
        reason = "Currently starting but not optimal"
        priority = 2
    elif not is_starter and is_optimal:
        recommendation = "🔥 SHOULD START"
        reason = "Not starting but should be in lineup"
        priority = 0
    else:
        recommendation = "🪑 BENCH"
        reason = "Lower projection than starters"
        priority = 3
    
    all_roster_players.append({
        'name': name,
        'position': pos,
        'projection': proj_points,
        'is_starter': is_starter,
        'is_optimal': is_optimal,
        'recommendation': recommendation,
        'reason': reason,
        'priority': priority
    })

# Sort by priority (most important decisions first) then by projection
roster_df = pd.DataFrame(all_roster_players)
roster_df = roster_df.sort_values(['priority', 'projection'], ascending=[True, False])

# Display by position
positions = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']
for pos in positions:
    pos_players = roster_df[roster_df['position'] == pos]
    if not pos_players.empty:
        st.markdown(f"**{pos} Players:**")
        
        for _, player in pos_players.iterrows():
            # Color coding based on recommendation
            if "START" in player['recommendation']:
                st.success(f"{player['recommendation']} - {player['name']} — **{player['projection']:.1f} pts** | {player['reason']}")
            elif "CONSIDER BENCH" in player['recommendation']:
                st.warning(f"{player['recommendation']} - {player['name']} — **{player['projection']:.1f} pts** | {player['reason']}")
            elif "SHOULD START" in player['recommendation']:
                st.info(f"{player['recommendation']} - {player['name']} — **{player['projection']:.1f} pts** | {player['reason']}")
            else:
                st.write(f"{player['recommendation']} - {player['name']} — **{player['projection']:.1f} pts** | {player['reason']}")

# Summary stats
st.markdown("---")
st.markdown("### 📊 Roster Summary")
col1, col2, col3 = st.columns(3)

with col1:
    optimal_total = sum(p['points'] for slot in optimal.values() for p in slot)
    st.metric("Optimal Lineup Total", f"{optimal_total:.1f} pts")

with col2:
    current_starter_total = sum([get_projection(get_player_name(pid, players), working_projections) for pid in starters_ids])
    st.metric("Current Starters Total", f"{current_starter_total:.1f} pts")

with col3:
    potential_gain = optimal_total - current_starter_total
    st.metric("Potential Points Gain", f"{potential_gain:+.1f} pts", delta=f"{potential_gain:+.1f}")

# Bench Recommendations (keeping original section but simplified)
st.markdown("---")
st.markdown("### 🪑 Top Bench Options")
st.caption(f"Best bench players available - Based on {source_display}")
bench_df = get_bench_recommendations(player_ids, players, working_projections, optimal)
if bench_df.empty:
    st.write("No bench players found.")
else:
    for _, row in bench_df.head(5).iterrows():  # Show top 5 only
        st.write(f"- {row['name']} ({row['pos']}) — **{row['points']:.1f} pts**")
