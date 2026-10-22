import streamlit as st
import requests
import pandas as pd
import numpy as np
import os
import time
from datetime import datetime
from pandas.errors import EmptyDataError
from collections import Counter
from backtester import (
    load_backtest_data, 
    compute_model_metrics, 
    compute_positional_breakdown, 
    compute_extreme_misses,
    enrich_backtest_evaluations,
    build_historical_backtest_data
)
import auth_manager
import analytics_manager
import trade_engine

# ─── Config ───────────────────────────────────────────────────────────────────
PROJ_FILE       = "projections_combined.csv"
COMPARISON_FILE = "projections_combined_comparison.csv"
FALLBACK_FILE   = "projections_fallback.csv"
FRESHNESS_HOURS = 24

st.set_page_config(
    page_title="NFL Predictive Analytics & Lineup Optimizer", 
    page_icon=None, 
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Modern Minimalist Aesthetic Theme (Eucalyptus / Sage & Block Typography) ──
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

/* Global Canvas & Typography */
html, body, [class*="css"], [data-testid="stAppViewContainer"] {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
    background-color: #F8F9F7 !important;
    color: #141714 !important;
}

/* Block Headings */
h1, h2, h3, h4, h5, h6 {
    font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, sans-serif !important;
    letter-spacing: -0.02em !important;
    font-weight: 700 !important;
    color: #141714 !important;
}

/* Thin Minimalist Dividers */
hr {
    border: none !important;
    border-top: 1px solid #E2E7E2 !important;
    margin: 22px 0 !important;
}

/* Metric KPI Containers (Rhode / Summer Fridays clean boxes) */
div[data-testid="stMetric"] {
    background-color: #FFFFFF !important;
    border: 1px solid #E2E7E2 !important;
    border-radius: 6px !important;
    padding: 12px 16px !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02) !important;
}
div[data-testid="stMetricLabel"] {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: #5B705E !important;
}
div[data-testid="stMetricValue"] {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 1.55rem !important;
    font-weight: 700 !important;
    color: #141714 !important;
}

/* Minimalist Pill Tabs */
button[data-baseweb="tab"] {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.04em !important;
    text-transform: uppercase !important;
    padding: 8px 14px !important;
    border-radius: 4px !important;
    color: #626A62 !important;
    background-color: transparent !important;
    border: none !important;
    transition: all 0.15s ease !important;
}
button[data-baseweb="tab"]:hover {
    color: #141714 !important;
    background-color: #EEF2EE !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #141714 !important;
    background-color: #E2EBE2 !important;
}
div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"] {
    display: none !important;
}

/* Modern Matte Sage Buttons */
.stButton > button {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 0.76rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase !important;
    background-color: #5B705E !important;
    color: #FFFFFF !important;
    border-radius: 4px !important;
    border: none !important;
    padding: 7px 16px !important;
    transition: all 0.15s ease !important;
}
.stButton > button:hover {
    background-color: #4A5C4C !important;
    color: #FFFFFF !important;
}

/* Minimalist Light Sidebar */
section[data-testid="stSidebar"] {
    background-color: #F1F4F1 !important;
    border-right: 1px solid #E2E7E2 !important;
}
section[data-testid="stSidebar"] h2 {
    font-family: 'Space Grotesk', sans-serif !important;
    font-size: 0.78rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    color: #141714 !important;
}

/* Clean Info and Warning Cards */
div[data-testid="stAlert"] {
    border-radius: 4px !important;
    border: 1px solid #E2E7E2 !important;
    background-color: #FFFFFF !important;
    color: #141714 !important;
}

/* Progress bar color */
div[data-testid="stProgress"] > div > div > div > div {
    background-color: #5B705E !important;
}
</style>
""", unsafe_allow_html=True)

# NFL Team Abbreviation Mapping for Defenses
TEAM_ABBR_MAP = {
    'ARI': 'Arizona Cardinals', 'ATL': 'Atlanta Falcons', 'BAL': 'Baltimore Ravens',
    'BUF': 'Buffalo Bills', 'CAR': 'Carolina Panthers', 'CHI': 'Chicago Bears',
    'CIN': 'Cincinnati Bengals', 'CLE': 'Cleveland Browns', 'DAL': 'Dallas Cowboys',
    'DEN': 'Denver Broncos', 'DET': 'Detroit Lions', 'GB': 'Green Bay Packers',
    'HOU': 'Houston Texans', 'IND': 'Indianapolis Colts', 'JAX': 'Jacksonville Jaguars',
    'KC': 'Kansas City Chiefs', 'LAC': 'Los Angeles Chargers', 'LAR': 'Los Angeles Rams',
    'LV': 'Las Vegas Raiders', 'MIA': 'Miami Dolphins', 'MIN': 'Minnesota Vikings',
    'NE': 'New England Patriots', 'NO': 'New Orleans Saints', 'NYG': 'New York Giants',
    'NYJ': 'New York Jets', 'PHI': 'Philadelphia Eagles', 'PIT': 'Pittsburgh Steelers',
    'SEA': 'Seattle Seahawks', 'SF': 'San Francisco 49ers', 'TB': 'Tampa Bay Buccaneers',
    'TEN': 'Tennessee Titans', 'WAS': 'Washington Commanders'
}

# ─── Data Loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=600)
def get_sleeper_data(league_id):
    try:
        users   = requests.get(f'https://api.sleeper.app/v1/league/{league_id}/users', timeout=10).json()
        rosters = requests.get(f'https://api.sleeper.app/v1/league/{league_id}/rosters', timeout=10).json()
        league  = requests.get(f'https://api.sleeper.app/v1/league/{league_id}', timeout=10).json()
        players = requests.get('https://api.sleeper.app/v1/players/nfl', timeout=15).json()
        return users, rosters, players, league
    except Exception as e:
        st.error(f"Sleeper data load error: {e}")
        return [], [], {}, {}

@st.cache_data(ttl=600)
def get_sleeper_matchups(league_id, week):
    try:
        matchups = requests.get(f'https://api.sleeper.app/v1/league/{league_id}/matchups/{week}', timeout=10).json()
        return matchups if isinstance(matchups, list) else []
    except Exception as e:
        st.error(f"Error fetching matchups for week {week}: {e}")
        return []

@st.cache_data(ttl=60)
def load_projections():
    try:
        df = pd.read_csv(PROJ_FILE)
    except (FileNotFoundError, EmptyDataError):
        st.warning("Live projections unavailable. Using fallback data.")
        try:
            df = pd.read_csv(FALLBACK_FILE)
        except (FileNotFoundError, EmptyDataError):
            st.error("No projection data available. Please run weekly_scraper.py.")
            return pd.DataFrame({"player_name": [], "proj_points": [], "position": [], "source": []})
    
    df['player_name'] = df['player_name'].astype(str).str.strip()
    df['position']    = df['position'].astype(str).str.upper()
    df['proj_points'] = pd.to_numeric(df['proj_points'], errors='coerce')
    if 'source' not in df.columns:
        df['source'] = 'Combined'
    return df.dropna(subset=['proj_points', 'player_name'])

@st.cache_data(ttl=60)  
def load_comparison_data():
    try:
        df = pd.read_csv(COMPARISON_FILE)
        df['player_name'] = df['player_name'].astype(str).str.strip()
        df['proj_points'] = pd.to_numeric(df['proj_points'], errors='coerce')
        return df.dropna()
    except (FileNotFoundError, EmptyDataError):
        return pd.DataFrame()

def is_file_stale(path, max_age_hours=FRESHNESS_HOURS):
    if not os.path.exists(path):
        return True
    return (time.time() - os.path.getmtime(path)) > (max_age_hours * 3600)

# ─── Analytical Helpers ────────────────────────────────────────────────────────
def get_player_name(pid, players):
    pid_str = str(pid).upper()
    if pid_str in TEAM_ABBR_MAP:
        return TEAM_ABBR_MAP[pid_str]
    p = players.get(str(pid), {})
    name = p.get('full_name') or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
    return name if name else str(pid)

def get_player_position(pid, players):
    pid_str = str(pid).upper()
    if pid_str in TEAM_ABBR_MAP:
        return 'DEF'
    return players.get(str(pid), {}).get('position', 'UNK')

def get_projection(name, proj_df, source=None):
    if not name or name == 'Unknown':
        return 0.0
    
    clean_name = name.lower().replace('.', '').strip()
    
    # 1. Exact Name Match
    mask = proj_df['player_name'].str.lower().str.replace('.', '', regex=False) == clean_name
    if source and source != 'Best Available (Combined)':
        mask = mask & (proj_df['source'] == source)
    
    row = proj_df[mask]
    if not row.empty:
        return float(row['proj_points'].values[0])
    
    # 2. Defense Matching: match city, team name, or abbreviation
    for abbr, full_team in TEAM_ABBR_MAP.items():
        if clean_name in full_team.lower() or clean_name == abbr.lower():
            def_mask = (
                proj_df['player_name'].str.lower().str.contains(full_team.lower(), na=False) |
                proj_df['player_name'].str.lower().str.contains(abbr.lower(), na=False) |
                proj_df['player_name'].str.lower().str.contains(full_team.split()[-1].lower(), na=False)
            ) & (proj_df['position'].isin(['DEF', 'DST']))
            
            if source and source != 'Best Available (Combined)':
                def_mask = def_mask & (proj_df['source'] == source)
            def_row = proj_df[def_mask]
            if not def_row.empty:
                return float(def_row['proj_points'].max())

    # 3. Last Name Fallback
    parts = clean_name.split()
    if len(parts) > 1:
        last = parts[-1]
        last_mask = proj_df['player_name'].str.lower().str.endswith(last)
        if source and source != 'Best Available (Combined)':
            last_mask = last_mask & (proj_df['source'] == source)
        l_row = proj_df[last_mask]
        if not l_row.empty:
            return float(l_row['proj_points'].values[0])
            
    return 0.0

def calculate_player_range(name, proj_points, comp_df):
    if comp_df.empty:
        floor = round(max(proj_points * 0.65, 0), 1)
        ceil  = round(proj_points * 1.35, 1)
        return floor, ceil, 0.0
    
    p_rows = comp_df[comp_df['player_name'].str.lower() == name.lower()]
    if len(p_rows) > 1:
        pts = p_rows['proj_points'].values
        spread = round(abs(pts.max() - pts.min()), 1)
        floor = round(max(min(pts) * 0.85, 0), 1)
        ceil = round(max(pts) * 1.25, 1)
        return floor, ceil, spread
    else:
        floor = round(max(proj_points * 0.7, 0), 1)
        ceil = round(proj_points * 1.3, 1)
        return floor, ceil, 0.0

def build_optimal_lineup(player_ids, players, proj_df, comp_df, roster_positions):
    entries = []
    for pid in player_ids:
        name  = get_player_name(pid, players)
        pos   = get_player_position(pid, players)
        pts   = get_projection(name, proj_df)
        fl, cl, sp = calculate_player_range(name, pts, comp_df)
        entries.append({'id': pid, 'name': name, 'pos': pos, 'points': pts, 'floor': fl, 'ceil': cl, 'spread': sp})
        
    df = pd.DataFrame(entries).sort_values('points', ascending=False)
    lineup = []
    used = set()
    
    def assign_best(slot_name, eligible_positions):
        for _, r in df.iterrows():
            if r['id'] not in used and r['pos'] in eligible_positions:
                lineup.append({'slot': slot_name, 'player': r.to_dict()})
                used.add(r['id'])
                return True
        lineup.append({'slot': slot_name, 'player': None})
        return False
    
    position_counters = {}
    for slot in roster_positions:
        if slot in position_counters:
            position_counters[slot] += 1
            slot_name = f"{slot} {position_counters[slot]}"
        else:
            position_counters[slot] = 1
            total_count = roster_positions.count(slot)
            slot_name = f"{slot} 1" if total_count > 1 else slot
        
        if slot == 'QB': assign_best(slot_name, ['QB'])
        elif slot == 'RB': assign_best(slot_name, ['RB'])
        elif slot == 'WR': assign_best(slot_name, ['WR'])
        elif slot == 'TE': assign_best(slot_name, ['TE'])
        elif slot == 'K': assign_best(slot_name, ['K'])
        elif slot in ['DEF', 'DST']: assign_best(slot_name, ['DEF'])
        elif slot in ['FLEX', 'REC_FLEX', 'WRT']: assign_best(slot_name, ['RB', 'WR', 'TE'])
        elif slot in ['SUPER_FLEX', 'OP']: assign_best(slot_name, ['QB', 'RB', 'WR', 'TE'])
    
    return lineup

# ─── User Authentication & Persistent Session Control ─────────────────────────
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.current_user = None

# Check URL query param for saved session token (Persistent Login)
query_token = st.query_params.get("session")
if not st.session_state.authenticated and query_token:
    authenticated_user = auth_manager.verify_session_token(query_token)
    if authenticated_user:
        st.session_state.authenticated = True
        st.session_state.current_user = authenticated_user
        st.query_params["session"] = query_token

def render_login_screen():
    st.markdown("""
    <div style="text-align: center; margin: 40px auto 25px auto; max-width: 520px;">
        <div style="font-family: 'Space Grotesk', sans-serif; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.16em; text-transform: uppercase; color: #5B705E; margin-bottom: 6px;">
            Gridiron IQ // Access Gateway
        </div>
        <div style="font-family: 'Space Grotesk', sans-serif; font-size: 2.2rem; font-weight: 700; letter-spacing: -0.03em; color: #141714; line-height: 1.15;">
            NFL PREDICTIVE ANALYTICS
        </div>
        <div style="font-family: 'Plus Jakarta Sans', sans-serif; font-size: 0.88rem; color: #5E665E; margin-top: 8px;">
            Sign in to access personalized lineup optimization, 6-source consensus forecasts, and saved league tracking.
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    col_spacer1, col_card, col_spacer2 = st.columns([1, 1.4, 1])
    with col_card:
        tab_login, tab_register = st.tabs(["Sign In", "Create Account"])
        
        with tab_login:
            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
            username = st.text_input("Username", key="login_username", placeholder="e.g. Lucas18S or lucas")
            password = st.text_input("Password", type="password", key="login_password", placeholder="Enter your password")
            save_login = st.checkbox("Save login on this device (Loads saved leagues)", value=True, key="chk_save_login")
            
            if st.button("Enter Dashboard", use_container_width=True, key="btn_login_submit"):
                if not username or not password:
                    st.error("Please enter both username and password.")
                elif auth_manager.verify_credentials(username, password):
                    norm_user = username.strip().lower()
                    st.session_state.authenticated = True
                    st.session_state.current_user = norm_user
                    analytics_manager.track_login(norm_user)
                    if save_login:
                        token = auth_manager.create_session_token(norm_user)
                        st.query_params["session"] = token
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
                    
            with st.expander("Forgot Password?", expanded=False):
                st.markdown("<div style='font-size:0.75rem; color:#5E665E;'>Enter your username or recovery email to submit an access recovery request to the platform administrator (Lucas18S).</div>", unsafe_allow_html=True)
                recovery_ident = st.text_input("Username or Recovery Email", key="inp_rec_ident")
                if st.button("Submit Reset Request", key="btn_sub_reset", use_container_width=True):
                    ok, msg = auth_manager.request_password_reset(recovery_ident)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)
                    
            st.markdown("""
            <div style="background-color: #F1F4F1; border: 1px solid #D6DFD6; border-radius: 4px; padding: 10px 12px; margin-top: 18px; font-size: 0.76rem; color: #4A564A;">
                <strong>Administrator Access:</strong> Username: <code>Lucas18S</code> | Password: <code>Packers</code><br>
                <strong>Standard Account:</strong> Username: <code>lucas</code> | Password: <code>fantasy2025</code><br>
                <span style="font-size: 0.72rem; color: #6A756A;">Or register your own custom account under the 'Create Account' tab.</span>
            </div>
            """, unsafe_allow_html=True)
            
        with tab_register:
            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
            reg_username = st.text_input("New Username", key="reg_username", placeholder="Choose username (min 3 chars)")
            reg_password = st.text_input("New Password", type="password", key="reg_password", placeholder="Choose password (min 4 chars)")
            reg_confirm  = st.text_input("Confirm Password", type="password", key="reg_confirm", placeholder="Repeat password")
            reg_email    = st.text_input("Recovery Email (Optional)", key="reg_email", placeholder="Used only if you forget your password")
            
            st.markdown("<div style='font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #5B705E; margin-top: 14px;'>Initial League Setup</div>", unsafe_allow_html=True)
            reg_platform = st.selectbox("Platform", ["Sleeper", "ESPN"], key="reg_platform")
            reg_league_id = st.text_input("League ID", value="1337487447067492352" if reg_platform == "Sleeper" else "", key="reg_league_id", placeholder="e.g. 1337487447067492352")
            
            reg_save_login = st.checkbox("Save login on this device", value=True, key="chk_reg_save")
            
            if st.button("Create Account & Sign In", use_container_width=True, key="btn_register_submit"):
                if not reg_username or not reg_password:
                    st.error("Username and password are required.")
                elif reg_password != reg_confirm:
                    st.error("Passwords do not match.")
                else:
                    ok, msg = auth_manager.register_user(
                        reg_username, 
                        reg_password, 
                        email=reg_email,
                        initial_league_id=reg_league_id, 
                        platform=reg_platform
                    )
                    if ok:
                        norm_user = reg_username.strip().lower()
                        st.session_state.authenticated = True
                        st.session_state.current_user = norm_user
                        analytics_manager.track_login(norm_user)
                        if reg_save_login:
                            token = auth_manager.create_session_token(norm_user)
                            st.query_params["session"] = token
                        st.rerun()
                    else:
                        st.error(msg)

if not st.session_state.authenticated:
    render_login_screen()
    st.stop()

# ─── Editorial Brand Header (Rhode / Summer Fridays Inspired) ──────────────────
st.markdown("""
<div style="padding: 6px 0 20px 0; border-bottom: 1px solid #E2E7E2; margin-bottom: 24px;">
    <div style="font-family: 'Space Grotesk', sans-serif; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: #5B705E; margin-bottom: 4px;">
        Predictive Intelligence / Consensus Model
    </div>
    <div style="font-family: 'Space Grotesk', sans-serif; font-size: 2.3rem; font-weight: 700; letter-spacing: -0.03em; color: #141714; line-height: 1.1;">
        NFL PREDICTIVE ANALYTICS & OPTIMIZER
    </div>
    <div style="font-family: 'Plus Jakarta Sans', sans-serif; font-size: 0.9rem; color: #5E665E; margin-top: 6px;">
        Multi-source ensemble forecasting, matchup simulation, and historical backtesting.
    </div>
</div>
""", unsafe_allow_html=True)

projections = load_projections()
comp_data = load_comparison_data()

if is_file_stale(PROJ_FILE):
    st.warning("Projections data is over 24 hours old. Run `python weekly_scraper.py` to refresh.")

# ─── Sidebar Configuration ───────────────────────────────────────────────────
with st.sidebar:
    # User Profile & Logout Header
    current_username = st.session_state.get('current_user', 'lucas')
    current_user_data = auth_manager.get_user(current_username) or {}
    user_display = current_user_data.get("display_name", current_username)
    is_user_admin = auth_manager.is_admin(current_username)
    role_badge = "<span style='background-color:#5B705E; color:#FFFFFF; font-size:0.6rem; font-weight:700; padding:2px 6px; border-radius:3px; text-transform:uppercase; margin-left:6px;'>Admin</span>" if is_user_admin else ""
    
    st.markdown(f"""
    <div style="background-color: #FFFFFF; border: 1px solid #E2E7E2; border-radius: 6px; padding: 10px 14px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
        <div>
            <div style="font-family: 'Space Grotesk', sans-serif; font-size: 0.65rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #5B705E;">User Account</div>
            <div style="font-family: 'Space Grotesk', sans-serif; font-size: 1.05rem; font-weight: 700; color: #141714;">{user_display} {role_badge}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    with st.expander("Account & Recovery Email", expanded=False):
        curr_email = current_user_data.get("email", "")
        new_email = st.text_input("Recovery Email", value=curr_email, placeholder="e.g. you@example.com", key="side_user_email")
        if st.button("Save Recovery Email", key="btn_save_rec_email", use_container_width=True):
            auth_manager.update_user_email(current_username, new_email)
            st.success("Recovery email saved!")
            st.rerun()

    if st.button("Sign Out", key="btn_signout", use_container_width=True, help="Log out and clear saved session"):
        token = st.query_params.get("session")
        if token:
            auth_manager.revoke_session_token(current_username, token)
            del st.query_params["session"]
        st.session_state.authenticated = False
        st.session_state.current_user = None
        st.rerun()

    st.markdown("---")
    st.header("League Settings")
    
    user_info = auth_manager.get_user(current_username) or {}
    saved_leagues = user_info.get("saved_leagues", [])
    if not saved_leagues:
        saved_leagues = [{
            "id": "sleeper_main",
            "name": "Main Sleeper League",
            "platform": "Sleeper",
            "sleeper_league_id": "1337487447067492352",
            "espn_league_id": "",
            "espn_s2": "",
            "swid": "",
            "is_default": True
        }]
    
    league_options = [f"{l.get('name', 'League')} ({l.get('platform')})" for l in saved_leagues]
    league_options.append("+ Connect New League")
    
    # Determine default index if not already tracking in session state
    default_idx = 0
    for idx, l in enumerate(saved_leagues):
        if l.get("is_default"):
            default_idx = idx
            break
            
    if "current_league_idx" not in st.session_state or st.session_state["current_league_idx"] >= len(league_options):
        st.session_state["current_league_idx"] = default_idx

    def on_saved_league_change():
        selected = st.session_state.get("saved_leagues_select")
        if selected in league_options:
            st.session_state["current_league_idx"] = league_options.index(selected)
        # Clear selected manager so the team dropdown resets to the new league's managers
        if "selected_manager" in st.session_state:
            del st.session_state["selected_manager"]

    selected_league_str = st.selectbox(
        "Saved Leagues",
        league_options,
        index=st.session_state["current_league_idx"],
        key="saved_leagues_select",
        on_change=on_saved_league_change
    )
    
    sleeper_league_id = ""
    espn_league_id = ""
    espn_s2 = ""
    swid = ""
    
    if selected_league_str == "+ Connect New League":
        st.markdown("<div style='font-size:0.72rem; font-weight:700; letter-spacing:0.06em; text-transform:uppercase; color:#5B705E; margin-top:8px;'>New League Setup</div>", unsafe_allow_html=True)
        new_league_name = st.text_input("League Nickname", value="My League", key="new_league_name")
        league_platform = st.radio("Platform", ["Sleeper", "ESPN"], key="new_league_platform")
        if league_platform == "Sleeper":
            new_s_input = st.text_input("Sleeper League ID", value="", placeholder="e.g. 1337487447067492352", key="new_sleeper_id")
            new_e_input = ""
            new_s2_input = ""
            new_swid_input = ""
        else:
            new_s_input = ""
            new_e_input = st.text_input("ESPN League ID", value="", placeholder="e.g. 529882810", key="new_espn_id")
            new_s2_input = st.text_input("ESPN_S2 (Private)", type="password", key="new_espn_s2")
            new_swid_input = st.text_input("SWID (Private)", type="password", key="new_swid")
            
        make_default = st.checkbox("Set as default league", value=True, key="chk_new_default")
        if st.button("Save League to Profile", use_container_width=True, key="btn_save_new_league"):
            s_val = new_s_input.strip()
            e_val = new_e_input.strip()
            if (league_platform == "Sleeper" and s_val) or (league_platform == "ESPN" and e_val):
                auth_manager.save_user_league(current_username, {
                    "name": new_league_name.strip() or "My League",
                    "platform": league_platform,
                    "sleeper_league_id": s_val,
                    "espn_league_id": e_val,
                    "espn_s2": new_s2_input.strip(),
                    "swid": new_swid_input.strip(),
                    "is_default": make_default
                })
                # Immediately select the newly created league index on rerun
                st.session_state["current_league_idx"] = len(saved_leagues)
                if "saved_leagues_select" in st.session_state:
                    del st.session_state["saved_leagues_select"]
                if "selected_manager" in st.session_state:
                    del st.session_state["selected_manager"]
                st.cache_data.clear()
                st.success("League saved!")
                st.rerun()
            else:
                st.error("Please enter a valid League ID.")
    else:
        chosen_idx = league_options.index(selected_league_str)
        active_league_data = saved_leagues[chosen_idx]
        league_id_key = str(active_league_data.get("id", chosen_idx))
        
        league_platform = active_league_data.get("platform", "Sleeper")
        sleeper_league_id = str(active_league_data.get("sleeper_league_id", "")).strip()
        espn_league_id = str(active_league_data.get("espn_league_id", "")).strip()
        espn_s2 = active_league_data.get("espn_s2", "")
        swid = active_league_data.get("swid", "")
        
        with st.expander("League Settings & Edit", expanded=False):
            edit_name = st.text_input("Nickname", value=active_league_data.get("name", "League"), key=f"name_{league_id_key}")
            if league_platform == "Sleeper":
                upd_sleeper_id = st.text_input("Sleeper League ID", value=sleeper_league_id, key=f"s_id_{league_id_key}")
                upd_espn_id = ""
                upd_espn_s2 = ""
                upd_swid = ""
            else:
                upd_sleeper_id = ""
                upd_espn_id = st.text_input("ESPN League ID", value=espn_league_id, key=f"e_id_{league_id_key}")
                upd_espn_s2 = st.text_input("ESPN_S2", value=espn_s2, type="password", key=f"e_s2_{league_id_key}")
                upd_swid = st.text_input("SWID", value=swid, type="password", key=f"e_swid_{league_id_key}")
                
            set_as_def = st.checkbox("Set as default league", value=active_league_data.get("is_default", False), key=f"def_{league_id_key}")
            col_save, col_del = st.columns(2)
            with col_save:
                if st.button("Update", key=f"btn_upd_{league_id_key}", use_container_width=True):
                    active_league_data["name"] = edit_name.strip()
                    if league_platform == "Sleeper":
                        active_league_data["sleeper_league_id"] = upd_sleeper_id.strip()
                    else:
                        active_league_data["espn_league_id"] = upd_espn_id.strip()
                        active_league_data["espn_s2"] = upd_espn_s2.strip()
                        active_league_data["swid"] = upd_swid.strip()
                    active_league_data["is_default"] = set_as_def
                    auth_manager.save_user_league(current_username, active_league_data)
                    st.cache_data.clear()
                    st.success("Updated!")
                    st.rerun()
            with col_del:
                if len(saved_leagues) > 1 and st.button("Delete", key=f"btn_del_{league_id_key}", use_container_width=True):
                    auth_manager.delete_user_league(current_username, active_league_data["id"])
                    st.session_state["current_league_idx"] = 0
                    if "saved_leagues_select" in st.session_state:
                        del st.session_state["saved_leagues_select"]
                    if "selected_manager" in st.session_state:
                        del st.session_state["selected_manager"]
                    st.cache_data.clear()
                    st.warning("Deleted league.")
                    st.rerun()
    
    st.markdown("---")
    st.header("Model Settings")
    base_models = sorted([s for s in projections['source'].unique() if not s.startswith('Combined')])
    source_options = ['Best Available (Combined)'] + base_models
    selected_source = st.selectbox("Forecast Model", source_options)

    if st.button("Reload Projections", help="Clear cache and reload latest scraper projections"):
        st.cache_data.clear()
        st.rerun()

    # Week selection
    selected_week = st.number_input("NFL Week", min_value=1, max_value=18, value=7, step=1)

# Filter projection source
if selected_source == 'Best Available (Combined)':
    working_projections = projections[projections['source'].str.contains('Combined', na=False)]
    if working_projections.empty:
        working_projections = projections
else:
    working_projections = projections[projections['source'] == selected_source]

# Load Platform League Data
if league_platform == "Sleeper":
    if not sleeper_league_id:
        st.info("Enter your Sleeper League ID in the sidebar to load your roster.")
        st.stop()
    users, rosters, players, league_settings = get_sleeper_data(sleeper_league_id)
    all_positions = league_settings.get('roster_positions', [])
    non_starting_slots = ['BN', 'IR', 'TAXI', 'RES', 'PRACTICE_SQUAD']
    roster_positions = [pos for pos in all_positions if pos not in non_starting_slots]
    league_name = league_settings.get('name', 'Sleeper League')
else:
    if not espn_league_id:
        st.info("Enter your ESPN League ID in the sidebar to load your roster.")
        st.stop()
    try:
        from espn_api.football import League
        league = League(league_id=int(espn_league_id), year=2025, espn_s2=espn_s2 or None, swid=swid or None)
        users = [{'user_id': str(t.team_id), 'display_name': t.team_name or f"Team {t.team_id}"} for t in league.teams]
        players = requests.get('https://api.sleeper.app/v1/players/nfl').json()
        roster_positions = ['QB', 'RB', 'RB', 'WR', 'WR', 'TE', 'FLEX', 'DST', 'K']
        league_name = getattr(league.settings, 'name', 'ESPN League')
        rosters = []
        for team in league.teams:
            rosters.append({
                'owner_id': str(team.team_id),
                'roster_id': team.team_id,
                'players': [p.name for p in team.roster],
                'starters': [p.name for p in team.roster if getattr(p, 'lineupSlot', 0) not in [20, 21]]
            })
    except Exception as e:
        st.error(f"Error loading ESPN league: {e}")
        st.stop()

# Helper map: roster_id -> display_name
roster_id_to_name = {}
for r in rosters:
    rid = r.get('roster_id')
    oid = r.get('owner_id')
    d_name = next((u['display_name'] for u in users if u['user_id'] == oid), f"Team {rid}")
    roster_id_to_name[rid] = d_name

# Top KPIs
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1:
    st.metric("Total Players Tracked", len(projections['player_name'].unique()))
with col_m2:
    sources_available = projections['source'].unique()
    st.metric("Consensus Sources", len([s for s in sources_available if 'Combined' not in s]))
with col_m3:
    avg_proj = round(projections[projections['source'].str.contains('Combined', na=False)]['proj_points'].mean(), 1)
    st.metric("League Avg Projection", f"{avg_proj} pts" if not np.isnan(avg_proj) else "—")
with col_m4:
    last_mod = datetime.fromtimestamp(os.path.getmtime(PROJ_FILE)).strftime("%b %d, %H:%M") if os.path.exists(PROJ_FILE) else "None"
    st.metric("Pipeline Run", last_mod)

# ─── Tab Configuration with State Retention ──────────────────────────────────
is_admin_user = auth_manager.is_admin(st.session_state.get('current_user', ''))

TAB_OPTIONS = [
    "Lineup Optimizer", 
    "Matchup Simulator", 
    "Trade Analyzer",
    "Waiver Radar",
    "Projection Arbitrage", 
    "Position Tiers",
    "Model Backtesting"
]
if is_admin_user:
    TAB_OPTIONS.append("Admin Console")

def set_active_tab(tab_name):
    st.session_state['active_tab'] = tab_name
    analytics_manager.track_tab_view(tab_name, st.session_state.get('current_user', 'user'))

active_tab = st.session_state.get('active_tab', TAB_OPTIONS[0])
if active_tab not in TAB_OPTIONS:
    active_tab = TAB_OPTIONS[0]

# Track tab view
analytics_manager.track_tab_view(active_tab, st.session_state.get('current_user', 'user'))

tabs = st.tabs(TAB_OPTIONS, default=active_tab)

# ─── TAB 1: Lineup Optimizer ──────────────────────────────────────────────────
with tabs[0]:
    st.subheader(f"Roster Optimization: {league_name}")
    manager_names = {r['owner_id']: next((u['display_name'] for u in users if u['user_id'] == r['owner_id']), f"Team {r['owner_id']}") for r in rosters}
    manager_list = list(manager_names.values())
    if not manager_list:
        st.warning("No teams found for this league.")
        st.stop()
        
    if st.session_state.get('selected_manager') not in manager_list:
        st.session_state['selected_manager'] = manager_list[0]

    selected_manager = st.selectbox(
        "Select Team:", 
        manager_list,
        key="selected_manager",
        on_change=set_active_tab,
        args=("Lineup Optimizer",)
    )
    selected_roster = next((r for r in rosters if manager_names.get(r['owner_id']) == selected_manager), rosters[0] if rosters else {})
    
    player_ids = selected_roster.get('players', []) if selected_roster else []
    starters_ids = selected_roster.get('starters', []) if selected_roster else []

    optimal = build_optimal_lineup(player_ids, players, working_projections, comp_data, roster_positions)
    optimal_ids = {slot['player']['id'] for slot in optimal if slot['player']}

    col_opt, col_roster = st.columns([1, 1])

    with col_opt:
        st.subheader("Optimal Starting Lineup")
        total_opt = 0
        opt_data = []
        for slot in optimal:
            s_name = slot['slot']
            p = slot['player']
            if p:
                total_opt += p['points']
                opt_data.append({
                    "Slot": s_name,
                    "Player": f"{p['name']} ({p['pos']})",
                    "Proj": f"{p['points']:.1f}",
                    "Floor": f"{p['floor']:.1f}",
                    "Ceiling": f"{p['ceil']:.1f}"
                })
            else:
                opt_data.append({"Slot": s_name, "Player": "EMPTY", "Proj": "0.0", "Floor": "0.0", "Ceiling": "0.0"})
        st.dataframe(pd.DataFrame(opt_data), use_container_width=True, hide_index=True)
        st.caption(f"**Projected Total Score: {total_opt:.1f} pts**")

    with col_roster:
        st.subheader("Lineup Efficiency & Swaps")
        curr_total = sum([get_projection(get_player_name(pid, players), working_projections) for pid in starters_ids])
        diff = total_opt - curr_total
        
        if diff > 0.5:
            st.warning(f"Projected Gain: +{diff:.1f} pts achievable by adjusting starting lineup.")
        else:
            st.info("Starting lineup is currently fully optimized.")

        bad_starts = [pid for pid in starters_ids if pid not in optimal_ids]
        bench_promotions = [slot['player'] for slot in optimal if slot['player'] and slot['player']['id'] not in starters_ids]

        if bad_starts or bench_promotions:
            st.markdown("**Recommended Lineup Swaps:**")
            for b_pid in bad_starts:
                st.write(f"• **Bench:** {get_player_name(b_pid, players)} ({get_projection(get_player_name(b_pid, players), working_projections):.1f} pts)")
            for s_ply in bench_promotions:
                st.write(f"• **Start:** {s_ply['name']} ({s_ply['points']:.1f} pts)")

    # Complete Roster Breakdown
    st.markdown("---")
    st.subheader(f"Roster Breakdown: {selected_manager}")
    st.caption("All rostered players ranked by projected output with floor, ceiling, and source discrepancy spread.")

    full_roster_data = []
    for pid in player_ids:
        name = get_player_name(pid, players)
        pos = get_player_position(pid, players)
        pts = get_projection(name, working_projections)
        floor, ceil, spread = calculate_player_range(name, pts, comp_data)
        
        is_starter = pid in starters_ids
        is_optimal = pid in optimal_ids
        
        if is_optimal:
            status = "Optimal Starter"
        elif is_starter and not is_optimal:
            status = "Bench Candidate"
        else:
            status = "Bench"
            
        full_roster_data.append({
            "Status": status,
            "Player": name,
            "Pos": pos,
            "Proj Pts": pts,
            "Floor": floor,
            "Ceiling": ceil,
            "Spread (Δ)": spread
        })

    roster_display_df = pd.DataFrame(full_roster_data)
    if not roster_display_df.empty:
        roster_display_df['sort_order'] = roster_display_df['Status'].map({
            "Optimal Starter": 1,
            "Bench Candidate": 2,
            "Bench": 3
        }).fillna(4)
        
        roster_display_df = roster_display_df.sort_values(by=['sort_order', 'Proj Pts'], ascending=[True, False]).drop(columns=['sort_order'])

        st.dataframe(
            roster_display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Proj Pts": st.column_config.NumberColumn(format="%.1f"),
                "Floor": st.column_config.NumberColumn(format="%.1f"),
                "Ceiling": st.column_config.NumberColumn(format="%.1f"),
                "Spread (Δ)": st.column_config.NumberColumn(format="%.1f")
            }
        )

# ─── TAB 2: Matchup Simulator ────────────────────────────────────────────────
with tabs[1]:
    st.subheader(f"Week {selected_week} Matchup Simulator")
    st.markdown("Simulates head-to-head league matchups using optimal lineup projections, floor/ceiling volatility bands, and win probabilities.")

    if league_platform == "Sleeper":
        matchups_raw = get_sleeper_matchups(sleeper_league_id, selected_week)
        
        if not matchups_raw:
            st.info(f"No matchup schedule available from Sleeper for Week {selected_week}.")
        else:
            matchup_groups = {}
            for m in matchups_raw:
                mid = m.get('matchup_id')
                if mid is not None:
                    matchup_groups.setdefault(mid, []).append(m)

            matchup_labels = []
            matchup_lookup = {}
            for mid, m_list in sorted(matchup_groups.items()):
                if len(m_list) == 2:
                    t1_name = roster_id_to_name.get(m_list[0].get('roster_id'), f"Roster {m_list[0].get('roster_id')}")
                    t2_name = roster_id_to_name.get(m_list[1].get('roster_id'), f"Roster {m_list[1].get('roster_id')}")
                    label = f"Matchup {mid}: {t1_name} vs {t2_name}"
                    matchup_labels.append(label)
                    matchup_lookup[label] = (m_list[0], m_list[1])

            if matchup_labels:
                chosen_matchup = st.selectbox(
                    "Select Matchup to Analyze:", 
                    matchup_labels,
                    key="matchup_chosen_select",
                    on_change=set_active_tab,
                    args=("Matchup Simulator",)
                )
                team_a_m, team_b_m = matchup_lookup[chosen_matchup]

                rid_a = team_a_m.get('roster_id')
                rid_b = team_b_m.get('roster_id')
                
                r_obj_a = next((r for r in rosters if r.get('roster_id') == rid_a), {})
                r_obj_b = next((r for r in rosters if r.get('roster_id') == rid_b), {})
                
                pids_a = r_obj_a.get('players', team_a_m.get('players', []))
                pids_b = r_obj_b.get('players', team_b_m.get('players', []))

                opt_a = build_optimal_lineup(pids_a, players, working_projections, comp_data, roster_positions)
                opt_b = build_optimal_lineup(pids_b, players, working_projections, comp_data, roster_positions)

                pts_a = sum(s['player']['points'] for s in opt_a if s['player'])
                pts_b = sum(s['player']['points'] for s in opt_b if s['player'])

                floor_a = sum(s['player']['floor'] for s in opt_a if s['player'])
                floor_b = sum(s['player']['floor'] for s in opt_b if s['player'])

                ceil_a = sum(s['player']['ceil'] for s in opt_a if s['player'])
                ceil_b = sum(s['player']['ceil'] for s in opt_b if s['player'])

                # Win Probability Heuristic
                point_spread = pts_a - pts_b
                win_prob_a = round((1 / (1 + 10 ** (-point_spread / 25))) * 100, 1)
                win_prob_b = round(100 - win_prob_a, 1)

                name_a = roster_id_to_name.get(rid_a, "Team A")
                name_b = roster_id_to_name.get(rid_b, "Team B")

                st.markdown("---")
                col_h1, col_h2, col_h3 = st.columns(3)
                with col_h1:
                    st.metric(f"{name_a}", f"{pts_a:.1f} pts", delta=f"{point_spread:+.1f} vs Opp")
                    st.caption(f"Range: {floor_a:.1f} (Floor) — {ceil_a:.1f} (Ceiling)")
                    st.progress(win_prob_a / 100, text=f"Win Prob: {win_prob_a}%")
                
                with col_h2:
                    st.markdown("<h3 style='text-align: center; margin-top: 15px;'>VS</h3>", unsafe_allow_html=True)
                    favored = name_a if pts_a > pts_b else name_b
                    fav_pts = abs(point_spread)
                    st.info(f"Projected Winner: **{favored}** by **{fav_pts:.1f} pts**")

                with col_h3:
                    st.metric(f"{name_b}", f"{pts_b:.1f} pts", delta=f"{-point_spread:+.1f} vs Opp")
                    st.caption(f"Range: {floor_b:.1f} (Floor) — {ceil_b:.1f} (Ceiling)")
                    st.progress(win_prob_b / 100, text=f"Win Prob: {win_prob_b}%")

                # Slot-by-Slot Comparison Table
                st.markdown("### Starter Slot Advantage")
                slot_comparison = []
                max_slots = max(len(opt_a), len(opt_b))
                for i in range(max_slots):
                    slot_a = opt_a[i] if i < len(opt_a) else None
                    slot_b = opt_b[i] if i < len(opt_b) else None

                    s_name = (slot_a['slot'] if slot_a else slot_b['slot'])
                    pa = slot_a['player'] if slot_a else None
                    pb = slot_b['player'] if slot_b else None

                    pts1 = pa['points'] if pa else 0.0
                    pts2 = pb['points'] if pb else 0.0
                    diff = pts1 - pts2

                    slot_comparison.append({
                        "Slot": s_name,
                        f"{name_a} Starter": f"{pa['name']} ({pa['pos']})" if pa else "EMPTY",
                        f"{name_a} Proj": f"{pts1:.1f}",
                        f"{name_b} Starter": f"{pb['name']} ({pb['pos']})" if pb else "EMPTY",
                        f"{name_b} Proj": f"{pts2:.1f}",
                        "Advantage": f"{name_a} (+{diff:.1f})" if diff > 0 else (f"{name_b} (+{-diff:.1f})" if diff < 0 else "EVEN")
                    })

                st.dataframe(pd.DataFrame(slot_comparison), use_container_width=True, hide_index=True)

                # ─── Full Bench & Depth Comparison ───────────────────────────
                st.markdown("---")
                st.markdown("### Bench & Roster Depth Comparison")
                st.caption("Side-by-side breakdown of bench firepower and substitution depth.")

                opt_ids_a = {s['player']['id'] for s in opt_a if s['player']}
                opt_ids_b = {s['player']['id'] for s in opt_b if s['player']}

                bench_pids_a = [p for p in pids_a if p not in opt_ids_a]
                bench_pids_b = [p for p in pids_b if p not in opt_ids_b]

                def build_bench_records(pid_list):
                    records = []
                    for pid in pid_list:
                        pname = get_player_name(pid, players)
                        ppos = get_player_position(pid, players)
                        ppts = get_projection(pname, working_projections)
                        pfl, pcl, psp = calculate_player_range(pname, ppts, comp_data)
                        records.append({
                            'id': pid,
                            'name': pname,
                            'pos': ppos,
                            'points': ppts,
                            'floor': pfl,
                            'ceil': pcl,
                            'spread': psp
                        })
                    return sorted(records, key=lambda x: x['points'], reverse=True)

                bench_a = build_bench_records(bench_pids_a)
                bench_b = build_bench_records(bench_pids_b)

                total_bench_pts_a = sum(b['points'] for b in bench_a)
                total_bench_pts_b = sum(b['points'] for b in bench_b)
                bench_diff = total_bench_pts_a - total_bench_pts_b

                b_col1, b_col2, b_col3 = st.columns(3)
                with b_col1:
                    st.metric(f"{name_a} Total Bench Pts", f"{total_bench_pts_a:.1f} pts", delta=f"{bench_diff:+.1f} vs Opp")
                with b_col2:
                    deeper_bench = name_a if total_bench_pts_a > total_bench_pts_b else name_b
                    st.info(f"Deeper Reserves: **{deeper_bench}** (+{abs(bench_diff):.1f} pts)")
                with b_col3:
                    st.metric(f"{name_b} Total Bench Pts", f"{total_bench_pts_b:.1f} pts", delta=f"{-bench_diff:+.1f} vs Opp")

                # Bench side-by-side rows
                max_bench_len = max(len(bench_a), len(bench_b))
                bench_rows = []
                for i in range(max_bench_len):
                    pa = bench_a[i] if i < len(bench_a) else None
                    pb = bench_b[i] if i < len(bench_b) else None

                    pts1 = pa['points'] if pa else 0.0
                    pts2 = pb['points'] if pb else 0.0

                    bench_rows.append({
                        f"{name_a} Bench Player": f"{pa['name']} ({pa['pos']})" if pa else "—",
                        f"{name_a} Proj": f"{pts1:.1f}" if pa else "—",
                        f"{name_a} Range": f"{pa['floor']:.1f} - {pa['ceil']:.1f}" if pa else "—",
                        f"{name_b} Bench Player": f"{pb['name']} ({pb['pos']})" if pb else "—",
                        f"{name_b} Proj": f"{pts2:.1f}" if pb else "—",
                        f"{name_b} Range": f"{pb['floor']:.1f} - {pb['ceil']:.1f}" if pb else "—",
                    })

                st.dataframe(pd.DataFrame(bench_rows), use_container_width=True, hide_index=True)
            else:
                st.info("No matchups paired for this week.")
    else:
        st.info("ESPN Matchup fetching is available for Sleeper leagues.")

# ─── TAB 3: Trade Analyzer ───────────────────────────────────────────────────
with tabs[2]:
    st.markdown("""
    <div style="padding: 4px 0 16px 0; border-bottom: 1px solid #E2E7E2; margin-bottom: 20px;">
        <div style="font-family: 'Space Grotesk', sans-serif; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: #5B705E; margin-bottom: 4px;">
            Asset Valuation & Decision Intelligence // Real-Time Trade Engine
        </div>
        <div style="font-family: 'Space Grotesk', sans-serif; font-size: 1.85rem; font-weight: 700; letter-spacing: -0.02em; color: #141714;">
            TRADE ANALYZER & VALUE CALCULATOR
        </div>
        <div style="font-family: 'Plus Jakarta Sans', sans-serif; font-size: 0.88rem; color: #5E665E; margin-top: 4px;">
            Dual-engine evaluation: Cross-reference real-world market equity (FantasyCalc & KeepTradeCut) with true starting lineup point shifts.
        </div>
    </div>
    """, unsafe_allow_html=True)

    if not rosters:
        st.info("Connect your league in the sidebar to simulate trades across team rosters.")
    else:
        # Detect League Type from Settings
        is_dynasty_detected = (league_settings.get('type') == 2) if isinstance(league_settings, dict) else False
        is_superflex_detected = any(pos in ['SUPER_FLEX', 'OP'] for pos in roster_positions) or roster_positions.count('QB') > 1

        # Valuation Settings Bar
        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            trade_mode = st.radio(
                "Valuation Format", 
                ["Dynasty (Asset Lifecycle & Picks)", "Redraft (Single-Season EV)"], 
                index=0 if is_dynasty_detected else 1, 
                horizontal=True,
                key="trade_mode_radio"
            )
        with col_c2:
            qb_mode = st.radio(
                "Quarterback Format", 
                ["1 QB", "Superflex / 2QB"], 
                index=1 if is_superflex_detected else 0, 
                horizontal=True,
                key="trade_qb_radio"
            )
        with col_c3:
            scoring_mode = st.radio(
                "Scoring Format", 
                ["Full PPR", "Half PPR", "Standard"], 
                index=0, 
                horizontal=True,
                key="trade_ppr_radio"
            )

        is_dynasty_flag = ("Dynasty" in trade_mode)
        num_qbs_flag = 2 if "Superflex" in qb_mode else 1
        ppr_val = 1.0 if "Full" in scoring_mode else (0.5 if "Half" in scoring_mode else 0.0)

        # Load Market Data (FantasyCalc & KeepTradeCut)
        with st.spinner("Fetching market consensus trade values..."):
            market_data = trade_engine.fetch_market_values(is_dynasty=is_dynasty_flag, num_qbs=num_qbs_flag, ppr=ppr_val)

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

        # Manager Selection (Team A vs Team B)
        all_manager_names = list(manager_names.values())
        default_team_a_idx = all_manager_names.index(selected_manager) if selected_manager in all_manager_names else 0
        
        col_team_a, col_team_b = st.columns(2)
        with col_team_a:
            team_a_name = st.selectbox("Select Proposer (Team A)", all_manager_names, index=default_team_a_idx, key="sel_tr_team_a")
            team_a_roster_obj = next((r for r in rosters if manager_names.get(r['owner_id']) == team_a_name), rosters[0])
            team_a_pids = team_a_roster_obj.get('players', [])
            
        with col_team_b:
            other_team_names = [m for m in all_manager_names if m != team_a_name] or all_manager_names
            team_b_name = st.selectbox("Select Trade Partner (Team B)", other_team_names, index=0, key="sel_tr_team_b")
            team_b_roster_obj = next((r for r in rosters if manager_names.get(r['owner_id']) == team_b_name), rosters[1] if len(rosters) > 1 else rosters[0])
            team_b_pids = team_b_roster_obj.get('players', [])

        # Build Player Selection Options with Market Values (Grouped by Position, High-to-Low Value)
        def build_player_trade_options(pids):
            sorted_players = trade_engine.sort_roster_by_position_and_value(pids, players, market_data, is_dynasty_flag)
            options = []
            pid_map = {}
            for p in sorted_players:
                label = f"[{p['pos']}] {p['name']} ({p['team']}) — {p['val']:,} pts"
                options.append(label)
                pid_map[label] = p['id']
            return options, pid_map, sorted_players

        opts_a, map_a, list_a = build_player_trade_options(team_a_pids)
        opts_b, map_b, list_b = build_player_trade_options(team_b_pids)

        draft_picks_available = market_data.get("draft_picks", [])
        draft_pick_labels = [f"{dp['name']} — {dp['value']:,} pts" for dp in draft_picks_available]
        draft_pick_map = {f"{dp['name']} — {dp['value']:,} pts": dp for dp in draft_picks_available}

        # Player & Pick Multiselect Boxes
        col_sel_a, col_sel_b = st.columns(2)
        with col_sel_a:
            st.markdown(f"<div style='font-family:Space Grotesk; font-size:0.85rem; font-weight:700; color:#5B705E; text-transform:uppercase;'>Assets {team_a_name} Sends</div>", unsafe_allow_html=True)
            chosen_labels_a = st.multiselect(
                "Select Players:", 
                opts_a, 
                key="tr_sel_players_a", 
                placeholder="Choose players to send (grouped by position, high to low value)..."
            )
            chosen_pids_a = [map_a[lbl] for lbl in chosen_labels_a]
            
            chosen_picks_a = []
            if is_dynasty_flag and draft_pick_labels:
                chosen_pick_labels_a = st.multiselect(
                    "Include Draft Picks:", 
                    draft_pick_labels, 
                    key="tr_sel_picks_a", 
                    placeholder="Choose draft picks to send..."
                )
                chosen_picks_a = [draft_pick_map[lbl] for lbl in chosen_pick_labels_a]

            with st.expander(f"View {team_a_name}'s Full Roster (Grouped by Pos)", expanded=False):
                df_roster_a = pd.DataFrame([{
                    "Pos": p['pos'],
                    "Player": p['name'],
                    "Team": p['team'],
                    "Age": p['age'] if p['age'] is not None else "—",
                    "Market Value": f"{p['val']:,}",
                    "Weekly Proj": f"{get_projection(p['name'], working_projections):.1f}"
                } for p in list_a])
                st.dataframe(df_roster_a, use_container_width=True, hide_index=True)

        with col_sel_b:
            st.markdown(f"<div style='font-family:Space Grotesk; font-size:0.85rem; font-weight:700; color:#5B705E; text-transform:uppercase;'>Assets {team_b_name} Sends</div>", unsafe_allow_html=True)
            chosen_labels_b = st.multiselect(
                "Select Players:", 
                opts_b, 
                key="tr_sel_players_b", 
                placeholder="Choose players to receive (grouped by position, high to low value)..."
            )
            chosen_pids_b = [map_b[lbl] for lbl in chosen_labels_b]
            
            chosen_picks_b = []
            if is_dynasty_flag and draft_pick_labels:
                chosen_pick_labels_b = st.multiselect(
                    "Include Draft Picks:", 
                    draft_pick_labels, 
                    key="tr_sel_picks_b", 
                    placeholder="Choose draft picks to receive..."
                )
                chosen_picks_b = [draft_pick_map[lbl] for lbl in chosen_pick_labels_b]

            with st.expander(f"View {team_b_name}'s Full Roster (Grouped by Pos)", expanded=False):
                df_roster_b = pd.DataFrame([{
                    "Pos": p['pos'],
                    "Player": p['name'],
                    "Team": p['team'],
                    "Age": p['age'] if p['age'] is not None else "—",
                    "Market Value": f"{p['val']:,}",
                    "Weekly Proj": f"{get_projection(p['name'], working_projections):.1f}"
                } for p in list_b])
                st.dataframe(df_roster_b, use_container_width=True, hide_index=True)

        st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)

        # Execute Analysis if Assets Selected
        if chosen_pids_a or chosen_pids_b or chosen_picks_a or chosen_picks_b:
            trade_result = trade_engine.evaluate_trade(
                team_a_name=team_a_name,
                team_b_name=team_b_name,
                team_a_roster=team_a_pids,
                team_b_roster=team_b_pids,
                team_a_sends=chosen_pids_a,
                team_b_sends=chosen_pids_b,
                picks_a_sends=chosen_picks_a,
                picks_b_sends=chosen_picks_b,
                is_dynasty=is_dynasty_flag,
                market_data=market_data,
                players_meta=players,
                projections=working_projections,
                comp_data=comp_data,
                roster_positions=roster_positions,
                build_optimal_lineup_func=build_optimal_lineup
            )

            # Strategic Verdict Multi-Factor Breakdown Card
            badge_color = trade_result.get("badge_color", "#5B705E")
            breakdown_lines_html = "".join([
                f"""<div style="display: flex; align-items: baseline; gap: 10px; margin-top: 8px; font-size: 0.88rem; color: #374151;">
                    <span style="font-weight: 700; color: #1F2937; min-width: 165px; display: inline-block;">&bull; {item['category']}:</span>
                    <span style="color: #4B5563;">{item['text']}</span>
                </div>""" for item in trade_result.get("breakdown_lines", [])
            ])

            st.markdown(f"""
            <div style="background-color: #FFFFFF; border: 1px solid #E2E7E2; border-left: 5px solid {badge_color}; border-radius: 6px; padding: 18px 22px; margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <div style="font-family: 'Space Grotesk', sans-serif; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: {badge_color};">
                        Trade Verdict // Multi-Factor Analysis
                    </div>
                    <div style="background-color: #EEF2EE; color: #2D3A2F; font-size: 0.72rem; font-weight: 700; padding: 3px 10px; border-radius: 4px; letter-spacing: 0.05em;">
                        {trade_result['verdict_badge']}
                    </div>
                </div>
                <div style="font-family: 'Space Grotesk', sans-serif; font-size: 1.25rem; font-weight: 700; color: #141714; margin-bottom: 6px;">
                    {trade_result.get('verdict_headline', trade_result['verdict_badge'])}
                </div>
                <div style="font-family: 'Plus Jakarta Sans', sans-serif; font-size: 0.95rem; font-weight: 500; color: #374151; line-height: 1.45; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid #F1F4F1;">
                    {trade_result.get('verdict_summary', trade_result['verdict'])}
                </div>
                <div style="font-family: 'Plus Jakarta Sans', sans-serif;">
                    {breakdown_lines_html}
                </div>
            </div>
            """, unsafe_allow_html=True)

            # 4 Core KPI Metric Cards
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            with col_m1:
                st.metric(
                    f"{team_a_name} Lineup Impact", 
                    f"{trade_result['delta_score_a']:+.1f} pts/wk",
                    delta=f"{trade_result['delta_score_a']:+.1f} pts",
                    delta_color="normal"
                )
            with col_m2:
                st.metric(
                    f"{team_b_name} Lineup Impact", 
                    f"{trade_result['delta_score_b']:+.1f} pts/wk",
                    delta=f"{trade_result['delta_score_b']:+.1f} pts",
                    delta_color="normal"
                )
            with col_m3:
                shift_label = f"+{trade_result['market_diff_a']:,}" if trade_result['market_diff_a'] >= 0 else f"{trade_result['market_diff_a']:,}"
                st.metric(
                    "Market Value Shift (A)", 
                    f"{shift_label} pts",
                    delta=f"{trade_result['fairness_pct']}% Fair",
                    delta_color="off"
                )
            with col_m4:
                if is_dynasty_flag and trade_result['avg_age_a_sends'] and trade_result['avg_age_b_sends']:
                    age_diff = round(trade_result['avg_age_b_sends'] - trade_result['avg_age_a_sends'], 1)
                    st.metric(
                        "Dynasty Age Shift (A)", 
                        f"{trade_result['avg_age_b_sends']} yrs avg",
                        delta=f"{age_diff:+.1f} yrs"
                    )
                else:
                    st.metric("Trade Fairness Index", f"{trade_result['fairness_pct']}%", delta="Market Equity")

            st.markdown("---")

            # Side-by-Side Detailed Asset Breakdown
            col_table_a, col_table_b = st.columns(2)
            with col_table_a:
                st.subheader(f"Assets {team_a_name} Sends")
                df_a = pd.DataFrame(trade_result["team_a_gives"])
                if not df_a.empty:
                    df_a = df_a.rename(columns={"name": "Player / Pick", "pos": "Pos", "age": "Age", "value": "Market Value", "trend": "30-Day Trend"})
                    st.dataframe(df_a[["Player / Pick", "Pos", "Age", "Market Value", "30-Day Trend"]], use_container_width=True, hide_index=True)
                    st.caption(f"**Total Market Value Sent: {trade_result['val_a_sends']:,} pts**")
                else:
                    st.info("No assets selected from Team A.")

            with col_table_b:
                st.subheader(f"Assets {team_b_name} Sends")
                df_b = pd.DataFrame(trade_result["team_b_gives"])
                if not df_b.empty:
                    df_b = df_b.rename(columns={"name": "Player / Pick", "pos": "Pos", "age": "Age", "value": "Market Value", "trend": "30-Day Trend"})
                    st.dataframe(df_b[["Player / Pick", "Pos", "Age", "Market Value", "30-Day Trend"]], use_container_width=True, hide_index=True)
                    st.caption(f"**Total Market Value Sent: {trade_result['val_b_sends']:,} pts**")
                else:
                    st.info("No assets selected from Team B.")

            # Strategic Counter-Balance Suggestions
            trade_suggestions = trade_engine.generate_balancing_suggestions(
                team_a_name=team_a_name,
                team_b_name=team_b_name,
                team_a_roster=team_a_pids,
                team_b_roster=team_b_pids,
                team_a_sends=chosen_pids_a,
                team_b_sends=chosen_pids_b,
                trade_result=trade_result,
                market_data=market_data,
                players_meta=players,
                projections=working_projections,
                comp_data=comp_data,
                roster_positions=roster_positions,
                is_dynasty=is_dynasty_flag,
                build_optimal_lineup_func=build_optimal_lineup,
                get_projection_func=get_projection
            )

            suggestions_list = trade_suggestions.get("suggestions", [])
            if suggestions_list:
                deficit_team = trade_suggestions.get("deficit_team", "Receiving Team")
                surplus_team = trade_suggestions.get("surplus_team", "Trade Partner")
                target_gap = trade_suggestions.get("target_gap", 0)

                st.markdown("""
                <div style="margin-top: 24px; margin-bottom: 8px; padding-top: 16px; border-top: 1px solid #E2E7E2;">
                    <div style="font-family: 'Space Grotesk', sans-serif; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #5B705E; margin-bottom: 4px;">
                        Negotiation Intelligence // Counter-Offer Balancer
                    </div>
                    <div style="font-family: 'Space Grotesk', sans-serif; font-size: 1.35rem; font-weight: 700; letter-spacing: -0.01em; color: #141714;">
                        SUGGESTED ASSETS TO BALANCE THIS TRADE
                    </div>
                </div>
                """, unsafe_allow_html=True)

                st.markdown(f"""
                <div style="font-family: 'Plus Jakarta Sans', sans-serif; font-size: 0.88rem; color: #5E665E; margin-bottom: 14px;">
                    Currently, <b>{deficit_team}</b> sends more market value than they receive (gap of <b>{target_gap:,} pts</b>). 
                    To bring this deal into parity or incentivize {deficit_team} to accept, ask <b>{surplus_team}</b> to include one of these 3 targeted options:
                </div>
                """, unsafe_allow_html=True)

                col_s1, col_s2, col_s3 = st.columns(3)
                cols = [col_s1, col_s2, col_s3]

                for idx, sug in enumerate(suggestions_list):
                    with cols[idx]:
                        p_info = sug.get("player", {})
                        badge_label = sug.get("badge", "SUGGESTION")
                        sug_name = sug.get("name", "Counter Suggestion")
                        rationale = sug.get("rationale", "")
                        new_fairness = sug.get("new_fairness", 100.0)

                        st.markdown(f"""
                        <div style="background-color: #FFFFFF; border: 1px solid #E2E7E2; border-top: 4px solid #5B705E; border-radius: 6px; padding: 14px; min-height: 210px; display: flex; flex-direction: column; justify-content: space-between;">
                            <div>
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                    <span style="font-family: 'Space Grotesk', sans-serif; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #5B705E;">
                                        {sug_name}
                                    </span>
                                    <span style="background-color: #EEF2EE; color: #2D3A2F; font-size: 0.65rem; font-weight: 700; padding: 2px 6px; border-radius: 3px;">
                                        {badge_label}
                                    </span>
                                </div>
                                <div style="font-family: 'Space Grotesk', sans-serif; font-size: 1.1rem; font-weight: 700; color: #141714; margin-bottom: 2px;">
                                    {p_info.get('name', 'Player')}
                                </div>
                                <div style="font-family: 'Plus Jakarta Sans', sans-serif; font-size: 0.8rem; color: #5E665E; margin-bottom: 8px;">
                                    {p_info.get('pos', '—')} // {p_info.get('team', '—')} &bull; Value: <b>{p_info.get('val', 0):,} pts</b> &bull; Proj: <b>{p_info.get('pts', 0.0):.1f} pts/wk</b>
                                </div>
                                <div style="font-family: 'Plus Jakarta Sans', sans-serif; font-size: 0.82rem; color: #374151; line-height: 1.4; margin-bottom: 10px;">
                                    {rationale}
                                </div>
                            </div>
                            <div style="background-color: #F8F9F7; border: 1px solid #E2E7E2; border-radius: 4px; padding: 6px 10px; font-size: 0.78rem; font-weight: 600; color: #2D3A2F; text-align: center;">
                                Resulting Parity: <b>{new_fairness}% Fair</b>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

            st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

            # Starting Lineup Shift Comparison Expander
            with st.expander("View Starting Lineup Optimization Details (Before vs After)", expanded=False):
                col_lo_a, col_lo_b = st.columns(2)
                with col_lo_a:
                    st.markdown(f"**{team_a_name} Starting Lineup Score**")
                    st.markdown(f"*Before Trade:* **{trade_result['score_a_before']} pts** $\rightarrow$ *After Trade:* **{trade_result['score_a_after']} pts** ({trade_result['delta_score_a']:+.1f} pts/wk)")
                with col_lo_b:
                    st.markdown(f"**{team_b_name} Starting Lineup Score**")
                    st.markdown(f"*Before Trade:* **{trade_result['score_b_before']} pts** $\rightarrow$ *After Trade:* **{trade_result['score_b_after']} pts** ({trade_result['delta_score_b']:+.1f} pts/wk)")

        else:
            st.info("Select players or draft picks from either team above to analyze market equity and simulated starting lineup point shifts.")
            
            # Quick Market Value Reference Leaderboard
            with st.expander("Market Consensus Trade Value Leaderboard (Top 15)", expanded=False):
                top_players = sorted(market_data.get("by_name", {}).values(), key=lambda x: x.get("consensus_value", 0), reverse=True)[:15]
                df_top = pd.DataFrame([{
                    "Rank": i+1,
                    "Player": p["name"],
                    "Pos": p["position"],
                    "Team": p["team"],
                    "Age": p.get("age") or "—",
                    "Consensus Value": f"{p.get('consensus_value', 0):,}",
                    "30-Day Trend": f"{p.get('trend30Day', 0):+d}"
                } for i, p in enumerate(top_players)])
                st.dataframe(df_top, use_container_width=True, hide_index=True)

# ─── TAB 4: Waiver Radar ─────────────────────────────────────────────────────
with tabs[3]:
    st.subheader("Waiver Wire & Free Agency Radar")
    st.markdown("Screens all unrostered free agents in your league, ranking them by consensus upside, model divergence, and floor/ceiling volatility.")

    if not rosters:
        st.info("Connect your league in the sidebar to identify unrostered free agents.")
    else:
        # Collect all rostered player names across all league teams
        all_rostered_pids = set()
        for r in rosters:
            all_rostered_pids.update(r.get('players', []))

        rostered_names_clean = set()
        for pid in all_rostered_pids:
            p_name = get_player_name(pid, players)
            if p_name and p_name != 'Unknown':
                rostered_names_clean.add(p_name.lower().replace('.', '').strip())

        # Filter distinct working projections for available players
        distinct_projections = working_projections.drop_duplicates(subset=['player_name', 'position']).copy()

        fa_records = []
        for _, row in distinct_projections.iterrows():
            pname = row['player_name']
            pname_clean = pname.lower().replace('.', '').strip()
            
            # Skip if currently on any league roster
            if pname_clean in rostered_names_clean:
                continue

            pos = row['position']
            pts = float(row['proj_points'])
            floor, ceil, spread = calculate_player_range(pname, pts, comp_data)
            
            # Boom / Upside ratio
            upside_ratio = round(((ceil - pts) / max(pts, 1.0)) * 100, 1)

            # Source list from comp_data
            p_rows = comp_data[comp_data['player_name'].str.lower() == pname.lower()]
            sources_list = list(p_rows['source'].unique()) if not p_rows.empty else [row.get('source', 'Model')]

            # Volatility Badge Tagging (Clean Editorial Labels)
            if spread >= 3.0 or (pts >= 7.0 and ceil >= 14.0 and spread >= 2.0):
                badge = "Ceiling Target"
                sort_prio = 1
            elif floor >= 7.5 and spread <= 2.2:
                badge = "Stable Floor"
                sort_prio = 2
            elif floor <= 3.5 and spread >= 2.5:
                badge = "Volatile Risk"
                sort_prio = 4
            elif pts >= 7.0:
                badge = "Consensus Flex"
                sort_prio = 3
            else:
                badge = "Speculative Dart"
                sort_prio = 5

            fa_records.append({
                'Badge': badge,
                'Player': pname,
                'Pos': pos,
                'Proj Pts': pts,
                'Floor': floor,
                'Ceiling': ceil,
                'Spread (Δ)': spread,
                'Upside %': f"+{upside_ratio:.0f}%",
                'Models': ", ".join(sources_list),
                'sort_prio': sort_prio
            })

        fa_df = pd.DataFrame(fa_records)

        if fa_df.empty:
            st.info("No free agents found matching current criteria.")
        else:
            # KPI Metrics
            boom_count = len(fa_df[fa_df['Badge'] == "Ceiling Target"])
            floor_count = len(fa_df[fa_df['Badge'] == "Stable Floor"])
            top_fa = fa_df.sort_values(by='Proj Pts', ascending=False).iloc[0]

            k_col1, k_col2, k_col3, k_col4 = st.columns(4)
            with k_col1:
                st.metric("Free Agents Tracked", len(fa_df))
            with k_col2:
                st.metric("Ceiling Targets", boom_count)
            with k_col3:
                st.metric("Stable Floor Streamers", floor_count)
            with k_col4:
                st.metric("Top Available FA", f"{top_fa['Player']} ({top_fa['Pos']})", f"{top_fa['Proj Pts']:.1f} pts")

            # Streaming Picks per Position Grid
            st.markdown("### Weekly Free Agent Streaming Recommendations")
            st.caption("Highest-rated waiver wire targets by position group:")
            stream_cols = st.columns(6)
            for idx, p_group in enumerate(["QB", "RB", "WR", "TE", "K", "DEF"]):
                group_fas = fa_df[fa_df['Pos'] == p_group].sort_values(by='Proj Pts', ascending=False)
                with stream_cols[idx]:
                    if not group_fas.empty:
                        best = group_fas.iloc[0]
                        st.markdown(f"**{p_group}**")
                        st.info(f"**{best['Player']}**\n\n**{best['Proj Pts']:.1f} pts**\n\n{best['Badge']}")
                    else:
                        st.markdown(f"**{p_group}**")
                        st.write("—")

            st.markdown("---")
            # Interactive Filter Bar
            fc1, fc2, fc3 = st.columns([1, 1, 2])
            with fc1:
                sel_pos = st.selectbox(
                    "Filter by Position", 
                    ["ALL", "QB", "RB", "WR", "TE", "K", "DEF"], 
                    key="fa_pos",
                    on_change=set_active_tab,
                    args=("Waiver Radar",)
                )
            with fc2:
                badge_options = ["ALL", "Ceiling Target", "Stable Floor", "Consensus Flex", "Volatile Risk", "Speculative Dart"]
                sel_badge = st.selectbox(
                    "Filter by Volatility Profile", 
                    badge_options, 
                    key="fa_badge",
                    on_change=set_active_tab,
                    args=("Waiver Radar",)
                )
            with fc3:
                min_pts = st.slider(
                    "Minimum Projected Points", 
                    min_value=0.0, 
                    max_value=20.0, 
                    value=3.0, 
                    step=0.5, 
                    key="fa_slider",
                    on_change=set_active_tab,
                    args=("Waiver Radar",)
                )

            filtered_fa = fa_df[fa_df['Proj Pts'] >= min_pts]
            if sel_pos != "ALL":
                filtered_fa = filtered_fa[filtered_fa['Pos'] == sel_pos]
            if sel_badge != "ALL":
                filtered_fa = filtered_fa[filtered_fa['Badge'] == sel_badge]

            filtered_fa = filtered_fa.sort_values(by=['sort_prio', 'Proj Pts'], ascending=[True, False]).drop(columns=['sort_prio'])

            st.dataframe(
                filtered_fa,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Proj Pts": st.column_config.NumberColumn(format="%.1f"),
                    "Floor": st.column_config.NumberColumn(format="%.1f"),
                    "Ceiling": st.column_config.NumberColumn(format="%.1f"),
                    "Spread (Δ)": st.column_config.NumberColumn(format="%.1f")
                }
            )

# ─── TAB 5: Projection Arbitrage ─────────────────────────────────────────────
with tabs[4]:
    st.subheader("Model Discrepancy & Arbitrage Matrix")
    st.markdown("Identifies players where individual projection models (**CBS**, **ESPN**, **FantasyPros**, **NFL**, **NumberFire**, **Sleeper**) have large disagreements. High spread indicates volatility and potential boom/bust candidates.")

    if not comp_data.empty and len(comp_data['source'].unique()) > 1:
        pivot_df = comp_data.pivot_table(index=['player_name', 'position'], columns='source', values='proj_points').reset_index()
        sources_found = [c for c in pivot_df.columns if c not in ['player_name', 'position']]
        if len(sources_found) >= 2:
            pivot_df['Spread (Delta)'] = (pivot_df[sources_found].max(axis=1) - pivot_df[sources_found].min(axis=1)).round(1)
            pivot_df['Consensus Avg'] = pivot_df[sources_found].mean(axis=1).round(1)
            pivot_df['Discrepancy %'] = ((pivot_df['Spread (Delta)'] / pivot_df['Consensus Avg']) * 100).round(1)
            
            spread_df = pivot_df.sort_values(by='Spread (Delta)', ascending=False).dropna(subset=['Spread (Delta)'])
            
            col_filter1, _ = st.columns([1, 3])
            with col_filter1:
                pos_choice = st.selectbox(
                    "Filter Position", 
                    ["ALL"] + list(spread_df['position'].unique()), 
                    key="disc_pos",
                    on_change=set_active_tab,
                    args=("Projection Arbitrage",)
                )
            
            if pos_choice != "ALL":
                spread_df = spread_df[spread_df['position'] == pos_choice]
            
            cols_to_show = ['player_name', 'position'] + sources_found + ['Spread (Delta)', 'Consensus Avg', 'Discrepancy %']
            st.dataframe(
                spread_df[cols_to_show],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Multiple projection sources must be present to compute discrepancy matrices.")
        st.info("Run `python weekly_scraper.py` to populate multiple sources into `projections_combined_comparison.csv`.")

# ─── TAB 6: Position Tiers ───────────────────────────────────────────────────
with tabs[5]:
    st.subheader("Position Consensus Tiers")
    pos_selected = st.selectbox(
        "Select Position Group", 
        ["QB", "RB", "WR", "TE", "K", "DEF"], 
        key="tier_pos",
        on_change=set_active_tab,
        args=("Position Tiers",)
    )
    
    tier_data = working_projections[working_projections['position'] == pos_selected].sort_values(by='proj_points', ascending=False).copy()
    
    if not tier_data.empty:
        tier_data['Rank'] = range(1, len(tier_data) + 1)
        top_val = tier_data['proj_points'].iloc[0]
        tier_data['Tier'] = ((top_val - tier_data['proj_points']) // 3 + 1).astype(int)
        
        col_t1, col_t2 = st.columns([2, 1])
        with col_t1:
            st.dataframe(
                tier_data[['Rank', 'Tier', 'player_name', 'proj_points', 'source']],
                use_container_width=True,
                hide_index=True
            )
        with col_t2:
            st.markdown(f"**Top Tier {pos_selected}s:**")
            tier_1 = tier_data[tier_data['Tier'] == 1]
            for _, r in tier_1.iterrows():
                st.write(f"• **{r['player_name']}** — {r['proj_points']:.1f} pts")
    else:
        st.write("No players found for this position.")

# ─── TAB 7: Model Backtesting ────────────────────────────────────────────────
with tabs[6]:
    st.subheader("Model Accuracy & Empirical Backtesting")
    st.markdown("Evaluates all 6 forecast models against ground-truth NFL box-score performances across completed weeks. Analyzes Mean Absolute Error (MAE), Root Mean Squared Error (RMSE), systematic model bias, rank correlation (Spearman ρ), and ensemble error reduction.")

    c_info, c_btn = st.columns([3, 1])
    with c_info:
        st.caption("Automated Weekly Cycle: Ground-truth box scores ingest every Tuesday morning following Monday Night Football to re-evaluate all models.")
    with c_btn:
        if st.button("Pull Latest Box Scores", key="refresh_bt_scores", help="Re-query NFL ground truth scores and rebuild backtesting evaluations", on_click=set_active_tab, args=("Model Backtesting",)):
            with st.spinner("Ingesting latest box scores from Sleeper API..."):
                build_historical_backtest_data()
                st.cache_data.clear()
                st.rerun()

    backtest_df = load_backtest_data()
    if backtest_df.empty:
        st.info("No historical backtest data found. Run `python backtester.py` to generate the evaluation dataset.")
    else:
        # 1. Summary Metrics
        metrics_df = compute_model_metrics(backtest_df)
        best_overall = metrics_df.iloc[0]
        
        # Calculate ensemble error reduction vs individual models
        standalone_mae = metrics_df[metrics_df['Model'] != 'Combined']['MAE'].mean()
        combined_mae = metrics_df[metrics_df['Model'] == 'Combined']['MAE'].values[0]
        ensemble_gain = ((standalone_mae - combined_mae) / standalone_mae) * 100.0

        best_corr = metrics_df.sort_values(by='Spearman ρ', ascending=False).iloc[0]
        min_bias = metrics_df.iloc[metrics_df['Bias'].abs().argmin()]

        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.metric("Top Overall Model", f"{best_overall['Model']}", f"{best_overall['MAE']:.2f} MAE")
        with k2:
            st.metric("Consensus Error Reduction", f"{ensemble_gain:+.1f}%", help="Error reduction from multi-source ensemble vs standalone models")
        with k3:
            st.metric("Best Rank Correlation", f"{best_corr['Model']}", f"{best_corr['Spearman ρ']:.3f} ρ")
        with k4:
            st.metric("Evaluated Sample Size", f"{len(backtest_df):,} players", f"Weeks 1–{backtest_df['week'].max()}")

        st.markdown("---")

        # 2. Accuracy Comparison Leaderboard
        st.markdown("### Projection Model Accuracy Leaderboard")
        st.caption("Standard Machine Learning model evaluation metrics (lower MAE & RMSE = higher accuracy; Spearman ρ measures ranking quality):")
        
        st.dataframe(
            metrics_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "MAE": st.column_config.NumberColumn("Mean Absolute Error (MAE)", format="%.2f", help="Average point deviation per player"),
                "RMSE": st.column_config.NumberColumn("Root Mean Sq Error (RMSE)", format="%.2f", help="Penalizes large outlier misses"),
                "Bias": st.column_config.NumberColumn("Model Bias (Mean Error)", format="%+.2f", help="Negative = under-projects, Positive = over-projects"),
                "Spearman ρ": st.column_config.NumberColumn("Spearman Rank Correlation (ρ)", format="%.3f", help="Monotonic ranking accuracy (0-1)"),
                "Pearson r": st.column_config.NumberColumn("Pearson Correlation (r)", format="%.3f"),
                "Within ±3 Pts %": st.column_config.NumberColumn("Within ±3.0 Pts (%)", format="%.1f%%", help="Percentage of projections within 3 pts of actual")
            }
        )

        st.markdown("---")

        # 3. Visualizations & Positional Specialists
        c_chart, c_spec = st.columns([1, 1])

        with c_chart:
            st.markdown("### Mean Absolute Error by Source")
            st.caption("Lower error indicates sharper, more reliable median projections:")
            chart_df = metrics_df.set_index('Model')[['MAE']]
            st.bar_chart(chart_df, color="#5B705E")

        with c_spec:
            st.markdown("### Positional Specialist Benchmark")
            st.caption("Which specific model is sharpest for each fantasy position:")
            pos_df = compute_positional_breakdown(backtest_df)
            
            # Format clean view
            pos_display = pos_df[['Position', 'Samples', 'Top Specialist Model', 'Top Specialist MAE', 'Combined MAE']]
            st.dataframe(
                pos_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Top Specialist MAE": st.column_config.NumberColumn(format="%.2f"),
                    "Combined MAE": st.column_config.NumberColumn(format="%.2f")
                }
            )

        st.markdown("---")

        # 4. Tactical Model Playbook (Manager Lineup Rules)
        st.markdown("### Tactical Lineup Playbook: Which Model to Trust & When")
        st.caption("Actionable decision rules translating empirical backtesting metrics into weekly lineup strategies:")

        pb1, pb2, pb3, pb4 = st.columns(4)
        with pb1:
            st.markdown("""
            **Lead Protection (Floor)**
            * **Trust:** `CBS Sports` & `Combined`
            * **Why:** Lowest downside variance & negative error bias (-0.35).
            * **Playbook:** When favored by $\ge 12$ pts, start players with strong CBS/Consensus agreement to secure high weekly floors.
            """)
        with pb2:
            st.markdown("""
            **Underdog Rally (Ceiling)**
            * **Trust:** `NumberFire`
            * **Why:** Captured 38% more +10+ pt spike weeks than conservative baselines.
            * **Playbook:** When facing a top scoring team, swap neutral flex options for players where NumberFire is bullish over consensus.
            """)
        with pb3:
            st.markdown("""
            **Positional Specialists**
            * **QB:** `CBS Sports` (5.93 MAE)
            * **RB & WR:** `NumberFire` (4.95 & 5.11 MAE)
            * **TE & K:** `ESPN` (4.87 & 3.77 MAE)
            * **DEF:** `NumberFire` (4.15 MAE)
            * **Playbook:** Break tiebreakers using each source's positional specialty.
            """)
        with pb4:
            st.markdown("""
            **The Ensemble Advantage**
            * **Trust:** `Combined Consensus`
            * **Why:** Delivers **+2.4%** error reduction over individual models ($r = 0.587$).
            * **Playbook:** Multi-source aggregation cancels out single-source modeling biases. In neutral matchups, always start the Consensus pick.
            """)

        st.markdown("---")

        # 5. Interactive Historical Accuracy & Matchup Inspector
        st.markdown("### Historical Accuracy & Performance Inspector")
        st.caption("Inspect actual player box-score points versus pre-game forecasts across completed weeks. Search any player, filter by position or outcome, and see which model had the sharpest forecast:")

        eval_df = enrich_backtest_evaluations(backtest_df)

        fc1, fc2, fc3, fc4 = st.columns([1, 1, 1.3, 1.5])
        with fc1:
            avail_weeks = ["All Weeks"] + [f"Week {w}" for w in sorted(eval_df['week'].unique())]
            sel_week = st.selectbox(
                "NFL Week",
                avail_weeks,
                key="bt_week",
                on_change=set_active_tab,
                args=("Model Backtesting",)
            )
        with fc2:
            sel_pos = st.selectbox(
                "Position",
                ["ALL", "QB", "RB", "WR", "TE", "K", "DEF"],
                key="bt_pos",
                on_change=set_active_tab,
                args=("Model Backtesting",)
            )
        with fc3:
            outcome_options = [
                "ALL Outcomes",
                "Bullseye (Within ±2.0 pts)",
                "On Target (Within ±4.0 pts)",
                "Ceiling Spike (+5.0+ pts)",
                "Floor Bust (-5.0+ pts)"
            ]
            sel_outcome = st.selectbox(
                "Performance Outcome",
                outcome_options,
                key="bt_outcome",
                on_change=set_active_tab,
                args=("Model Backtesting",)
            )
        with fc4:
            search_query = st.text_input(
                "Search Player Name",
                placeholder="e.g. CeeDee Lamb, Josh Allen",
                key="bt_search",
                on_change=set_active_tab,
                args=("Model Backtesting",)
            )

        # Apply Filters
        filtered_eval = eval_df.copy()
        if sel_week != "All Weeks":
            wk_num = int(sel_week.replace("Week ", ""))
            filtered_eval = filtered_eval[filtered_eval['week'] == wk_num]
        
        if sel_pos != "ALL":
            filtered_eval = filtered_eval[filtered_eval['position'] == sel_pos]

        if sel_outcome == "Bullseye (Within ±2.0 pts)":
            filtered_eval = filtered_eval[filtered_eval['Abs Error'] <= 2.0]
        elif sel_outcome == "On Target (Within ±4.0 pts)":
            filtered_eval = filtered_eval[filtered_eval['Abs Error'] <= 4.0]
        elif sel_outcome == "Ceiling Spike (+5.0+ pts)":
            filtered_eval = filtered_eval[filtered_eval['Delta'] >= 5.0]
        elif sel_outcome == "Floor Bust (-5.0+ pts)":
            filtered_eval = filtered_eval[filtered_eval['Delta'] <= -5.0]

        if search_query.strip():
            filtered_eval = filtered_eval[filtered_eval['player_name'].str.lower().str.contains(search_query.strip().lower(), na=False)]

        # Sorting logic
        if sel_outcome == "Ceiling Spike (+5.0+ pts)":
            filtered_eval = filtered_eval.sort_values(by='Delta', ascending=False)
        elif sel_outcome == "Floor Bust (-5.0+ pts)":
            filtered_eval = filtered_eval.sort_values(by='Delta', ascending=True)
        else:
            filtered_eval = filtered_eval.sort_values(by=['week', 'actual_pts'], ascending=[False, False])

        # Summary Metrics for Filtered Slice
        if not filtered_eval.empty:
            k1, k2, k3, k4 = st.columns(4)
            with k1:
                st.metric("Filtered Games", f"{len(filtered_eval):,}")
            with k2:
                avg_err = filtered_eval['Abs Error'].mean()
                st.metric("Avg Point Error (MAE)", f"{avg_err:.2f} pts")
            with k3:
                bullseye_rate = (filtered_eval['Abs Error'] <= 2.0).mean() * 100.0
                st.metric("Bullseye Rate (±2 pts)", f"{bullseye_rate:.1f}%")
            with k4:
                top_source = filtered_eval['Closest Model'].mode().values[0] if not filtered_eval['Closest Model'].empty else "—"
                hits = (filtered_eval['Closest Model'] == top_source).sum()
                st.metric("Sharpest Model in Slice", f"{top_source}", f"{hits} wins")

            show_all_sources = st.checkbox(
                "Display individual model projections side-by-side (CBS, ESPN, FantasyPros, NFL, NumberFire, Sleeper)",
                value=False,
                key="bt_show_models",
                on_change=set_active_tab,
                args=("Model Backtesting",)
            )

            base_cols = ['week', 'player_name', 'position', 'Combined', 'actual_pts', 'Delta', 'Accuracy Status', 'Closest Model']
            model_cols = ['CBS', 'ESPN', 'FantasyPros', 'NFL', 'NumberFire', 'Sleeper'] if show_all_sources else []
            final_cols = base_cols + model_cols

            col_config = {
                "Consensus Proj": st.column_config.NumberColumn(format="%.1f", help="Multi-source average pre-game projection"),
                "Actual Pts": st.column_config.NumberColumn(format="%.1f", help="Ground-truth official box-score PPR points"),
                "Divergence (Δ)": st.column_config.NumberColumn(format="%+.1f", help="Actual Pts - Consensus Proj (+ = Boom, - = Bust)"),
                "Closest Source": st.column_config.TextColumn(help="The individual source model whose pre-game forecast came closest to the actual box-score score")
            }
            if show_all_sources:
                for mc in model_cols:
                    col_config[mc] = st.column_config.NumberColumn(format="%.1f")

            display_df = filtered_eval[final_cols].rename(columns={
                'week': 'Week',
                'player_name': 'Player',
                'position': 'Pos',
                'Combined': 'Consensus Proj',
                'actual_pts': 'Actual Pts',
                'Delta': 'Divergence (Δ)',
                'Accuracy Status': 'Status Badge',
                'Closest Model': 'Closest Source'
            })

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config=col_config
            )
        else:
            st.info("No player performances found matching the selected filters. Try broadening your criteria.")

# ─── TAB 8: Administrator Console (Admin Lucas18S Exclusive) ───────────────────
if is_admin_user:
    with tabs[7]:
        st.markdown("""
        <div style="padding: 4px 0 16px 0; border-bottom: 1px solid #E2E7E2; margin-bottom: 20px;">
            <div style="font-family: 'Space Grotesk', sans-serif; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: #5B705E; margin-bottom: 4px;">
                Platform Governance & Telemetry // Master Admin
            </div>
            <div style="font-family: 'Space Grotesk', sans-serif; font-size: 1.85rem; font-weight: 700; letter-spacing: -0.02em; color: #141714;">
                ADMINISTRATOR CONSOLE
            </div>
            <div style="font-family: 'Plus Jakarta Sans', sans-serif; font-size: 0.88rem; color: #5E665E; margin-top: 4px;">
                Monitor user engagement, audit saved leagues, analyze feature view counts, and manage credential recovery requests.
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        all_users = auth_manager.load_users()
        analytics_data = analytics_manager.get_analytics_summary()
        pending_resets = auth_manager.get_reset_requests()
        
        total_registered = len(all_users)
        total_leagues_count = sum(len(u.get("saved_leagues", [])) for u in all_users.values())
        avg_leagues_per_user = round(total_leagues_count / total_registered, 1) if total_registered > 0 else 0
        
        tab_views_dict = analytics_data.get("tab_views", {})
        top_tab = max(tab_views_dict.items(), key=lambda x: x[1])[0] if tab_views_dict else "Lineup Optimizer"
        
        # 1. Top KPI Metric Cards
        col_a1, col_a2, col_a3, col_a4 = st.columns(4)
        with col_a1:
            st.metric("Total Users", total_registered)
        with col_a2:
            st.metric("Total Tracked Leagues", total_leagues_count)
        with col_a3:
            st.metric("Avg Leagues / User", f"{avg_leagues_per_user}")
        with col_a4:
            st.metric("Most Viewed Tab", top_tab)
            
        st.markdown("---")
        
        # 2. Tab Views & Feature Engagement Telemetry
        st.subheader("Feature Telemetry & Tab Popularity")
        st.caption("Aggregated view counts across all registered user sessions.")
        
        col_chart, col_stat = st.columns([1.6, 1])
        with col_chart:
            sorted_views = sorted(tab_views_dict.items(), key=lambda x: x[1], reverse=True)
            df_views = pd.DataFrame(sorted_views, columns=["Feature Tab", "Total Views"])
            st.bar_chart(df_views.set_index("Feature Tab"), color="#5B705E", horizontal=True)
            
        with col_stat:
            st.markdown("<div style='font-family:Space Grotesk; font-size:0.85rem; font-weight:700; color:#5B705E; text-transform:uppercase;'>Usage Breakdown</div>", unsafe_allow_html=True)
            total_views_sum = sum(tab_views_dict.values())
            for tab_name_iter, view_count in sorted_views:
                pct = round((view_count / total_views_sum * 100), 1) if total_views_sum > 0 else 0
                st.markdown(f"**{tab_name_iter}**: {view_count:,} views ({pct}%)")
            st.caption(f"Total Platform Sessions: **{analytics_data.get('total_logins', 0)}**")
            
        st.markdown("---")
        
        # 3. Credential Recovery & Password Reset Center
        st.subheader("Credential Recovery & Password Resets")
        if pending_resets:
            st.warning(f"{len(pending_resets)} Pending Password Reset Request(s)")
            for req in pending_resets:
                req_id = req.get("id")
                req_user = req.get("username")
                req_email = req.get("email") or "Not provided"
                req_time = req.get("requested_at", "")[:16].replace("T", " ")
                
                with st.container():
                    st.markdown(f"""
                    <div style="background-color: #FFFDF5; border: 1px solid #E6D8B5; border-radius: 6px; padding: 12px 16px; margin-bottom: 10px;">
                        <div style="font-weight: 700; color: #8A6D3B;">Request ID: {req_id} | User: <code>{req_user}</code></div>
                        <div style="font-size: 0.85rem; color: #555;">Recovery Email: {req_email} | Submitted: {req_time}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    col_rp1, col_rp2 = st.columns([2, 1])
                    with col_rp1:
                        new_p = st.text_input(f"New Password for {req_user}", value="Packers2025", key=f"inp_reset_{req_id}")
                    with col_rp2:
                        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
                        if st.button("Set Password & Resolve", key=f"btn_res_{req_id}", use_container_width=True):
                            ok, msg = auth_manager.resolve_reset_request(req_id, new_p)
                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
        else:
            st.info("No pending password reset requests. All user accounts operating normally.")
            
        with st.expander("Manual Password Override Tool", expanded=False):
            st.markdown("<div style='font-size:0.85rem; color:#5E665E;'>Select any user to immediately override and assign a new password.</div>", unsafe_allow_html=True)
            target_account = st.selectbox("Select Target User", list(all_users.keys()), key="sel_target_pwd")
            override_new_pwd = st.text_input("New Password", key="inp_override_pwd", placeholder="Enter new password (min 4 chars)")
            if st.button("Apply New Password", key="btn_apply_override_pwd"):
                if not override_new_pwd:
                    st.error("Please enter a new password.")
                else:
                    ok, msg = auth_manager.admin_set_password(target_account, override_new_pwd)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)

        st.markdown("---")
        
        # 4. User Directory & League Portfolio Auditor
        st.subheader("Registered Users & League Distribution")
        
        user_rows = []
        platform_counts = {"Sleeper": 0, "ESPN": 0}
        
        for u_key, u_val in all_users.items():
            leagues = u_val.get("saved_leagues", [])
            for l in leagues:
                plat = l.get("platform", "Sleeper")
                platform_counts[plat] = platform_counts.get(plat, 0) + 1
                
            user_rows.append({
                "Username": u_val.get("display_name", u_key),
                "Role": u_val.get("role", "user").upper(),
                "Recovery Email": u_val.get("email") or "—",
                "Total Leagues": len(leagues),
                "Created Date": u_val.get("created_at", "")[:10]
            })
            
        col_tbl, col_plat = st.columns([2, 1])
        with col_tbl:
            st.dataframe(pd.DataFrame(user_rows), use_container_width=True, hide_index=True)
            
        with col_plat:
            st.markdown("<div style='font-family:Space Grotesk; font-size:0.85rem; font-weight:700; color:#5B705E; text-transform:uppercase;'>Platform Share</div>", unsafe_allow_html=True)
            df_plat = pd.DataFrame(list(platform_counts.items()), columns=["Platform", "Total Leagues"])
            st.bar_chart(df_plat.set_index("Platform"), color="#5B705E")
            
        with st.expander("Danger Zone: Delete User Account", expanded=False):
            deletable_users = [u for u in all_users.keys() if u != "lucas18s"]
            if deletable_users:
                user_to_delete = st.selectbox("Select Account to Delete", deletable_users, key="sel_del_user")
                st.warning(f"Permanently removes '{user_to_delete}' and all their saved leagues from the database.")
                if st.button(f"Delete Account '{user_to_delete}'", key="btn_confirm_del", type="primary"):
                    ok, msg = auth_manager.admin_delete_user(user_to_delete)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            else:
                st.info("No standard user accounts eligible for deletion.")


