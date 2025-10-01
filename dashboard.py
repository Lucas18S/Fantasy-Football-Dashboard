import streamlit as st
import requests
import pandas as pd
import os
import time
from datetime import datetime
from pandas.errors import EmptyDataError

# ─── Config ───────────────────────────────────────────────────────────────────
PROJ_FILE       = "projections_combined.csv"
COMPARISON_FILE = "projections_combined_comparison.csv"
FALLBACK_FILE   = "projections_fallback.csv"
FRESHNESS_HOURS = 24

# ─── Data Loading ──────────────────────────────────────────────────────────────
@st.cache_data
def get_data(league_id):
    try:
        users   = requests.get(f'https://api.sleeper.app/v1/league/{league_id}/users').json()
        rosters = requests.get(f'https://api.sleeper.app/v1/league/{league_id}/rosters').json()
        league  = requests.get(f'https://api.sleeper.app/v1/league/{league_id}').json()
        players = requests.get('https://api.sleeper.app/v1/players/nfl').json()
        return users, rosters, players, league
    except Exception as e:
        st.error(f"Data load error: {e}")
        return [], [], {}, {}

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

def get_projection(name, proj_df, source=None):
    """Get projection for a player, optionally filtered by source"""
    mask = proj_df['player_name'].str.lower() == name.lower()
    if source:
        mask = mask & (proj_df['source'] == source)
    row = proj_df[mask]
    return float(row['proj_points'].values[0]) if not row.empty else 0.0

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

def build_optimal_lineup(player_ids, players, proj_df, roster_positions):
    """Build optimal lineup based on league-specific roster configuration"""
    entries = []
    for pid in player_ids:
        name  = get_player_name(pid, players)
        pos   = get_player_position(pid, players)
        pts   = get_projection(name, proj_df)
        entries.append({'id': pid, 'name': name, 'pos': pos, 'points': pts})
    df = pd.DataFrame(entries).sort_values('points', ascending=False)

    # Initialize lineup with actual roster positions
    from collections import defaultdict
    lineup = defaultdict(list)
    used = set()
    
    def assign(slot, eligible_positions):
        """Assign best available player for this slot"""
        for _, r in df.iterrows():
            if r['id'] not in used and r['pos'] in eligible_positions:
                lineup[slot].append(r)
                used.add(r['id'])
                return True
        return False
    
    # Process roster positions in order
    for slot in roster_positions:
        # Define eligible positions for each slot type
        if slot == 'QB':
            assign(slot, ['QB'])
        elif slot == 'RB':
            assign(slot, ['RB'])
        elif slot == 'WR':
            assign(slot, ['WR'])
        elif slot == 'TE':
            assign(slot, ['TE'])
        elif slot == 'K':
            assign(slot, ['K'])
        elif slot in ['DEF', 'DST']:
            assign('DEF', ['DEF'])
        elif slot in ['FLEX', 'REC_FLEX', 'WRT']:
            assign('FLEX', ['RB', 'WR', 'TE'])
        elif slot in ['SUPER_FLEX', 'OP']:
            assign('SUPERFLEX', ['QB', 'RB', 'WR', 'TE'])
        elif slot == 'RB/WR':
            assign('RB/WR', ['RB', 'WR'])
        elif slot == 'WR/TE':
            assign('WR/TE', ['WR', 'TE'])
        elif slot == 'RB/WR/TE':
            assign('RB/WR/TE', ['RB', 'WR', 'TE'])
        elif slot == 'TQB':
            assign('TQB', ['QB'])
    
    return dict(lineup)

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

# Sidebar for league configuration
with st.sidebar:
    st.header("⚙️ Your League")
    
    league_platform = st.radio(
        "Choose your league platform:",
        ["Sleeper", "ESPN"],
        help="Select which fantasy platform your league uses"
    )
    
    # Initialize variables
    sleeper_league_id = ""
    espn_league_id = ""
    espn_s2 = ""
    swid = ""
    
    if league_platform == "Sleeper":
        st.subheader("🏈 Sleeper League")
        sleeper_league_id = st.text_input(
            "Sleeper League ID",
            value="",
            placeholder="e.g., 1185263580356419584",
            help="Find this in your Sleeper league URL: sleeper.app/leagues/YOUR_LEAGUE_ID"
        )
        if not sleeper_league_id:
            st.info("Enter your League ID to get started!")
            st.markdown("**How to find it:** Open your league on Sleeper and copy the ID from the URL")
    
    else:  # ESPN
        st.subheader("🏈 ESPN League")
        espn_league_id = st.text_input(
            "ESPN League ID",
            value="",
            placeholder="e.g., 529882810",
            help="Find this in your ESPN league URL"
        )
        
        with st.expander("🔐 ESPN Authentication (for private leagues)", expanded=False):
            st.caption("Private leagues require these cookies from your browser:")
            espn_s2 = st.text_input(
                "ESPN_S2 Cookie",
                value="",
                type="password",
                help="Find in browser cookies after logging into ESPN"
            )
            swid = st.text_input(
                "SWID Cookie",
                value="",
                type="password",
                help="Format: {XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}"
            )
            st.caption("⚠️ These are stored only in your browser session")

# Load league data based on selected platform
if league_platform == "Sleeper":
    if not sleeper_league_id:
        st.info("👈 Enter your Sleeper League ID in the sidebar to continue")
        st.stop()
    users, rosters, players, league_settings = get_data(sleeper_league_id)
    
    # Extract roster configuration from Sleeper league settings
    all_positions = league_settings.get('roster_positions', [])
    # Filter out bench, IR, taxi, and other non-starting slots - we only want starting positions
    non_starting_slots = ['BN', 'IR', 'TAXI', 'RES', 'PRACTICE_SQUAD']
    roster_positions = [pos for pos in all_positions if pos not in non_starting_slots]
    league_name = league_settings.get('name', 'Your League')
else:  # ESPN
    if not espn_league_id:
        st.info("👈 Enter your ESPN League ID in the sidebar to continue")
        st.stop()
    
    # Load ESPN league data
    try:
        from espn_api.football import League
        
        if espn_s2 and swid:
            league = League(league_id=int(espn_league_id), year=2025, espn_s2=espn_s2, swid=swid)
        else:
            league = League(league_id=int(espn_league_id), year=2025)
        
        # Convert ESPN data to similar format as Sleeper
        users = [{'user_id': str(team.team_id), 'display_name': team.team_name or f"Team {team.team_id}"} 
                 for team in league.teams]
        
        # Get all NFL players for name lookups
        players_response = requests.get('https://api.sleeper.app/v1/players/nfl').json()
        players = players_response
        
        # Extract roster configuration from ESPN league settings
        roster_positions = []
        league_name = league.settings.name if hasattr(league.settings, 'name') else 'Your League'
        
        # Map ESPN lineup slot IDs to position names (based on ESPN API documentation)
        espn_slots = {
            0: 'QB', 2: 'RB', 4: 'WR', 6: 'TE', 
            16: 'DST', 17: 'K', 23: 'FLEX',
            7: 'OP',  # Superflex/OP slot
            20: 'BENCH', 21: 'IR'
        }
        
        # Detect roster positions from actual team lineups
        try:
            if league.teams:
                # Get lineup slots from first team's roster
                slot_counts = {}
                sample_team = league.teams[0]
                
                for player in sample_team.roster:
                    slot_id = player.lineupSlot
                    if slot_id not in [20, 21]:  # Exclude bench and IR
                        slot_counts[slot_id] = slot_counts.get(slot_id, 0) + 1
                
                # Build roster positions list
                for slot_id in sorted(slot_counts.keys()):
                    position = espn_slots.get(slot_id, f'SLOT_{slot_id}')
                    count = slot_counts[slot_id]
                    roster_positions.extend([position] * count)
            
            # Fallback if detection didn't work
            if not roster_positions:
                st.warning("⚠️ Could not detect ESPN roster configuration. Using standard lineup format.")
                roster_positions = ['QB', 'RB', 'RB', 'WR', 'WR', 'TE', 'FLEX', 'DST', 'K']
        
        except Exception as e:
            st.warning(f"⚠️ Error parsing ESPN roster settings: {e}. Using standard lineup.")
            roster_positions = ['QB', 'RB', 'RB', 'WR', 'WR', 'TE', 'FLEX', 'DST', 'K']
        
        # Build rosters from ESPN teams
        rosters = []
        for team in league.teams:
            roster_players = []
            starters = []
            for player in team.roster:
                # Try to find player in Sleeper database by name matching
                player_name = player.name
                matching_player = None
                
                # Try exact match first
                for pid, pdata in players.items():
                    if pdata.get('full_name', '').lower() == player_name.lower():
                        matching_player = pid
                        break
                
                # If no exact match, try partial match (for cases like "D. Smith" vs "David Smith")
                if not matching_player:
                    for pid, pdata in players.items():
                        sleeper_name = pdata.get('full_name', '').lower()
                        # Check if last names match and first initial matches
                        if sleeper_name and player_name.lower().split()[-1] in sleeper_name:
                            # Also check if positions match to avoid wrong player
                            if hasattr(player, 'position') and player.position == pdata.get('position'):
                                matching_player = pid
                                break
                
                if matching_player:
                    roster_players.append(matching_player)
                    # Check if player is in starting lineup
                    if hasattr(player, 'lineupSlot') and player.lineupSlot not in [20, 21]:
                        starters.append(matching_player)
            
            rosters.append({
                'owner_id': str(team.team_id),
                'players': roster_players,
                'starters': starters
            })
    
    except Exception as e:
        st.error(f"❌ Could not load ESPN league: {e}")
        st.caption("Make sure your League ID is correct and add authentication cookies if it's a private league.")
        st.stop()
projections = load_projections()
comparison_data = load_comparison_data()

# Display league roster configuration
st.markdown("---")
st.markdown(f"### 🏈 {league_name}")

# Count positions
from collections import Counter
position_counts = Counter(roster_positions)

# Display roster configuration
st.markdown("**Roster Configuration:**")
roster_display = []
# Define display order for positions
position_order = ['QB', 'RB', 'WR', 'TE', 'RB/WR', 'WR/TE', 'RB/WR/TE', 'FLEX', 'REC_FLEX', 'WRT', 'SUPER_FLEX', 'OP', 'TQB', 'DST', 'DEF', 'K']
for position, count in sorted(position_counts.items(), key=lambda x: (
    position_order.index(x[0]) if x[0] in position_order else 99, x[0]
)):
    roster_display.append(f"{count} {position}")

st.info(" • ".join(roster_display))

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

# Debug info
st.caption(f"📊 Found {len(player_ids)} players on roster")

optimal = build_optimal_lineup(player_ids, players, working_projections, roster_positions)

# Check if optimal lineup is empty
if not optimal or all(len(plist) == 0 for plist in optimal.values()):
    st.error("❌ Could not generate optimal lineup. This might be because:")
    st.write("- Player names don't match between ESPN and projection data")
    st.write("- No projections available for your players")
    st.write(f"- Roster has {len(player_ids)} players")
    st.write(f"- Roster positions: {roster_positions}")
else:
    total   = 0
    for slot, plist in optimal.items():
        if plist:  # Only show slots that have players
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
