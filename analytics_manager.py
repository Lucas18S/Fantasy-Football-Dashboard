import os
import json
from datetime import datetime
from typing import Dict, Any

ANALYTICS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analytics.json")

def _load_raw_analytics() -> Dict[str, Any]:
    if not os.path.exists(ANALYTICS_FILE):
        return {
            "tab_views": {
                "Lineup Optimizer": 24,
                "Matchup Simulator": 18,
                "Trade Analyzer": 14,
                "Waiver Radar": 15,
                "Projection Arbitrage": 9,
                "Position Tiers": 7,
                "Model Backtesting": 11
            },
            "total_logins": 12,
            "user_activity": {},
            "daily_views": {}
        }
    try:
        with open(ANALYTICS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {ANALYTICS_FILE}: {e}")
        return {
            "tab_views": {},
            "total_logins": 0,
            "user_activity": {},
            "daily_views": {}
        }

def _save_raw_analytics(data: Dict[str, Any]):
    try:
        with open(ANALYTICS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving {ANALYTICS_FILE}: {e}")

def track_tab_view(tab_name: str, username: str = "guest"):
    """Record a view for a given tab/feature."""
    if not tab_name:
        return
    data = _load_raw_analytics()
    tab_views = data.get("tab_views", {})
    tab_views[tab_name] = tab_views.get(tab_name, 0) + 1
    data["tab_views"] = tab_views
    
    today = datetime.now().strftime("%Y-%m-%d")
    daily = data.get("daily_views", {})
    daily[today] = daily.get(today, 0) + 1
    data["daily_views"] = daily
    
    if username and username != "guest":
        users_act = data.get("user_activity", {})
        users_act[username] = datetime.now().isoformat()
        data["user_activity"] = users_act
        
    _save_raw_analytics(data)

def track_login(username: str):
    """Record a user login event."""
    data = _load_raw_analytics()
    data["total_logins"] = data.get("total_logins", 0) + 1
    users_act = data.get("user_activity", {})
    users_act[username] = datetime.now().isoformat()
    data["user_activity"] = users_act
    _save_raw_analytics(data)

def get_analytics_summary() -> Dict[str, Any]:
    """Retrieve summarized analytics for admin reporting."""
    return _load_raw_analytics()
