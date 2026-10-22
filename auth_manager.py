import json
import os
import hashlib
import secrets
from datetime import datetime

from typing import Optional, Tuple, Dict, List, Any

USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")

def _hash_password(password: str, salt: str) -> str:
    """Hash a password with a unique salt using SHA-256."""
    return hashlib.sha256((salt + password).encode('utf-8')).hexdigest()

def load_users() -> Dict[str, Any]:
    """Load users from the JSON file, or seed default users if file doesn't exist."""
    if not os.path.exists(USERS_FILE):
        return _seed_default_users()
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("users", {})
    except Exception as e:
        print(f"Error loading {USERS_FILE}: {e}")
        return _seed_default_users()

def save_users(users: Dict[str, Any]):
    """Save users dictionary to the JSON database."""
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"users": users}, f, indent=2)
    except Exception as e:
        print(f"Error saving {USERS_FILE}: {e}")

def _seed_default_users() -> Dict[str, Any]:
    """Create initial default user accounts with default league configuration."""
    users = {}
    # Create default user 'lucas' with password 'fantasy2025'
    salt = secrets.token_hex(16)
    users["lucas"] = {
        "username": "lucas",
        "salt": salt,
        "password_hash": _hash_password("fantasy2025", salt),
        "created_at": datetime.now().isoformat(),
        "session_tokens": [],
        "saved_leagues": [
            {
                "id": "sleeper_main",
                "name": "Main Sleeper League",
                "platform": "Sleeper",
                "sleeper_league_id": "1337487447067492352",
                "espn_league_id": "",
                "espn_s2": "",
                "swid": "",
                "is_default": True
            }
        ]
    }
    save_users(users)
    return users

def verify_credentials(username: str, password: str) -> bool:
    """Check if username and password match."""
    username = username.strip().lower()
    users = load_users()
    if username not in users:
        return False
    user = users[username]
    salt = user.get("salt", "")
    expected_hash = user.get("password_hash", "")
    return _hash_password(password, salt) == expected_hash

def register_user(username: str, password: str, initial_league_id: str = "1337487447067492352", platform: str = "Sleeper") -> Tuple[bool, str]:
    """Register a new user account."""
    username = username.strip().lower()
    if not username:
        return False, "Username cannot be empty."
    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password) < 4:
        return False, "Password must be at least 4 characters."
    
    users = load_users()
    if username in users:
        return False, f"Username '{username}' already exists. Please choose another."
    
    salt = secrets.token_hex(16)
    users[username] = {
        "username": username,
        "salt": salt,
        "password_hash": _hash_password(password, salt),
        "created_at": datetime.now().isoformat(),
        "session_tokens": [],
        "saved_leagues": [
            {
                "id": f"{platform.lower()}_primary",
                "name": f"My {platform} League",
                "platform": platform,
                "sleeper_league_id": initial_league_id if platform == "Sleeper" else "",
                "espn_league_id": initial_league_id if platform == "ESPN" else "",
                "espn_s2": "",
                "swid": "",
                "is_default": True
            }
        ]
    }
    save_users(users)
    return True, "Account created successfully."

def create_session_token(username: str) -> str:
    """Generate a persistent session token for 'Save Login' / remember me."""
    username = username.strip().lower()
    users = load_users()
    if username not in users:
        return ""
    token = secrets.token_urlsafe(32)
    tokens = users[username].get("session_tokens", [])
    # Limit max 10 active tokens per user
    if len(tokens) >= 10:
        tokens = tokens[-9:]
    tokens.append(token)
    users[username]["session_tokens"] = tokens
    save_users(users)
    return token

def verify_session_token(token: str) -> Optional[str]:
    """Verify if a session token is valid and return the associated username."""
    if not token:
        return None
    users = load_users()
    for username, data in users.items():
        if token in data.get("session_tokens", []):
            return username
    return None

def revoke_session_token(username: str, token: str):
    """Revoke a session token on logout."""
    username = username.strip().lower()
    users = load_users()
    if username in users:
        tokens = users[username].get("session_tokens", [])
        if token in tokens:
            tokens.remove(token)
            users[username]["session_tokens"] = tokens
            save_users(users)

def get_user(username: str) -> Optional[Dict[str, Any]]:
    """Get full user data dictionary."""
    users = load_users()
    return users.get(username.strip().lower())

def save_user_league(username: str, league_data: dict) -> bool:
    """Add or update a saved league in the user's profile."""
    username = username.strip().lower()
    users = load_users()
    if username not in users:
        return False
    
    leagues = users[username].get("saved_leagues", [])
    league_id = league_data.get("id") or secrets.token_hex(6)
    league_data["id"] = league_id
    
    # If this league is marked default, unset default on others
    if league_data.get("is_default"):
        for l in leagues:
            l["is_default"] = False
            
    # Check if updating existing
    updated = False
    for i, l in enumerate(leagues):
        if l.get("id") == league_id:
            leagues[i] = league_data
            updated = True
            break
            
    if not updated:
        leagues.append(league_data)
        
    users[username]["saved_leagues"] = leagues
    save_users(users)
    return True

def delete_user_league(username: str, league_id: str) -> bool:
    """Delete a saved league from the user's profile."""
    username = username.strip().lower()
    users = load_users()
    if username not in users:
        return False
    
    leagues = users[username].get("saved_leagues", [])
    new_leagues = [l for l in leagues if l.get("id") != league_id]
    
    # Ensure at least one default if leagues remain
    if new_leagues and not any(l.get("is_default") for l in new_leagues):
        new_leagues[0]["is_default"] = True
        
    users[username]["saved_leagues"] = new_leagues
    save_users(users)
    return True
