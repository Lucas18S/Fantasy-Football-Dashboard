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

def _load_data() -> Dict[str, Any]:
    """Load raw data structure from users.json."""
    if not os.path.exists(USERS_FILE):
        return _seed_initial_database()
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Ensure keys exist
            if "users" not in data:
                data["users"] = {}
            if "reset_requests" not in data:
                data["reset_requests"] = []
            return data
    except Exception as e:
        print(f"Error loading {USERS_FILE}: {e}")
        return _seed_initial_database()

def _save_data(data: Dict[str, Any]):
    """Save full data structure to users.json."""
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving {USERS_FILE}: {e}")

def _seed_initial_database() -> Dict[str, Any]:
    """Seed initial database with admin Lucas18S and default user."""
    users = {}
    
    # 1. Administrator Account: Lucas18S / Packers
    salt_admin = secrets.token_hex(16)
    users["lucas18s"] = {
        "username": "lucas18s",
        "display_name": "Lucas18S",
        "role": "admin",
        "email": "",
        "salt": salt_admin,
        "password_hash": _hash_password("Packers", salt_admin),
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
    
    # 2. Default standard account: lucas / fantasy2025
    salt_user = secrets.token_hex(16)
    users["lucas"] = {
        "username": "lucas",
        "display_name": "lucas",
        "role": "user",
        "email": "",
        "salt": salt_user,
        "password_hash": _hash_password("fantasy2025", salt_user),
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
    
    data = {
        "users": users,
        "reset_requests": []
    }
    _save_data(data)
    return data

def load_users() -> Dict[str, Any]:
    """Load users dictionary, ensuring Lucas18S exists as admin."""
    data = _load_data()
    users = data.get("users", {})
    
    # Ensure Lucas18S admin exists and password is set
    if "lucas18s" not in users:
        salt = secrets.token_hex(16)
        users["lucas18s"] = {
            "username": "lucas18s",
            "display_name": "Lucas18S",
            "role": "admin",
            "email": "",
            "salt": salt,
            "password_hash": _hash_password("Packers", salt),
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
        data["users"] = users
        _save_data(data)
    else:
        # Guarantee admin role on lucas18s
        if users["lucas18s"].get("role") != "admin":
            users["lucas18s"]["role"] = "admin"
            data["users"] = users
            _save_data(data)
            
    return users

def save_users(users: Dict[str, Any]):
    """Save updated users dict while keeping other data intact."""
    data = _load_data()
    data["users"] = users
    _save_data(data)

def is_admin(username: str) -> bool:
    """Check if the given username has administrator privileges."""
    if not username:
        return False
    norm = username.strip().lower()
    if norm == "lucas18s":
        return True
    user = get_user(norm)
    return bool(user and user.get("role") == "admin")

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

def register_user(username: str, password: str, email: str = "", initial_league_id: str = "1337487447067492352", platform: str = "Sleeper") -> Tuple[bool, str]:
    """Register a new user account with optional recovery email."""
    raw_user = username.strip()
    username = raw_user.lower()
    email = email.strip().lower()
    
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
        "display_name": raw_user,
        "role": "user",
        "email": email,
        "salt": salt,
        "password_hash": _hash_password(password, salt),
        "created_at": datetime.now().isoformat(),
        "session_tokens": [],
        "saved_leagues": [
            {
                "id": f"{platform.lower()}_primary",
                "name": f"My {platform} League",
                "platform": platform,
                "sleeper_league_id": initial_league_id.strip() if platform == "Sleeper" else "",
                "espn_league_id": initial_league_id.strip() if platform == "ESPN" else "",
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

def update_user_email(username: str, email: str) -> Tuple[bool, str]:
    """Update recovery email address for a user."""
    username = username.strip().lower()
    users = load_users()
    if username not in users:
        return False, "User not found."
    users[username]["email"] = email.strip().lower()
    save_users(users)
    return True, "Recovery email updated."

def request_password_reset(identity: str) -> Tuple[bool, str]:
    """Log a password reset request identified by username or recovery email."""
    identity = identity.strip().lower()
    if not identity:
        return False, "Please provide your username or recovery email."
        
    users = load_users()
    target_username = None
    target_email = ""
    
    # 1. Match by username
    if identity in users:
        target_username = identity
        target_email = users[identity].get("email", "")
    else:
        # 2. Match by email
        for u_name, u_data in users.items():
            if u_data.get("email", "").lower() == identity:
                target_username = u_name
                target_email = u_data.get("email", "")
                break
                
    if not target_username:
        return False, "No account found matching that username or email address."
        
    data = _load_data()
    requests_list = data.get("reset_requests", [])
    
    req_id = secrets.token_hex(6)
    new_request = {
        "id": req_id,
        "username": target_username,
        "email": target_email,
        "requested_at": datetime.now().isoformat(),
        "status": "pending"
    }
    requests_list.append(new_request)
    data["reset_requests"] = requests_list
    _save_data(data)
    
    display_user = users[target_username].get("display_name", target_username)
    return True, f"Reset request logged for '{display_user}'. The administrator (Lucas18S) has been notified in the Admin Panel to reset your access."

def get_reset_requests() -> List[Dict[str, Any]]:
    """Get all pending password reset requests."""
    data = _load_data()
    all_reqs = data.get("reset_requests", [])
    return [r for r in all_reqs if r.get("status") == "pending"]

def resolve_reset_request(request_id: str, new_password: str) -> Tuple[bool, str]:
    """Resolve a reset request by setting a new password for the user."""
    data = _load_data()
    all_reqs = data.get("reset_requests", [])
    target_req = next((r for r in all_reqs if r.get("id") == request_id), None)
    
    if not target_req:
        return False, "Reset request not found."
        
    username = target_req.get("username")
    ok, msg = admin_set_password(username, new_password)
    if not ok:
        return False, msg
        
    # Reload data fresh so we preserve the password change
    fresh_data = _load_data()
    fresh_reqs = fresh_data.get("reset_requests", [])
    for r in fresh_reqs:
        if r.get("id") == request_id:
            r["status"] = "resolved"
            r["resolved_at"] = datetime.now().isoformat()
            break
    fresh_data["reset_requests"] = fresh_reqs
    _save_data(fresh_data)
    return True, f"Password successfully updated for '{username}'."

def admin_set_password(target_username: str, new_password: str) -> Tuple[bool, str]:
    """Administrator password override for any user."""
    target_username = target_username.strip().lower()
    if len(new_password) < 4:
        return False, "New password must be at least 4 characters."
        
    users = load_users()
    if target_username not in users:
        return False, f"User '{target_username}' does not exist."
        
    salt = secrets.token_hex(16)
    users[target_username]["salt"] = salt
    users[target_username]["password_hash"] = _hash_password(new_password, salt)
    users[target_username]["session_tokens"] = []  # Clear active sessions to enforce new password
    save_users(users)
    return True, f"Password for '{target_username}' has been updated."

def admin_delete_user(target_username: str) -> Tuple[bool, str]:
    """Delete a user account (admin protected)."""
    target_username = target_username.strip().lower()
    if target_username in ["lucas18s"]:
        return False, "Cannot delete master administrator account."
        
    users = load_users()
    if target_username not in users:
        return False, f"User '{target_username}' not found."
        
    del users[target_username]
    save_users(users)
    return True, f"User '{target_username}' deleted."

def save_user_league(username: str, league_data: dict) -> bool:
    """Add or update a saved league in the user's profile."""
    username = username.strip().lower()
    users = load_users()
    if username not in users:
        return False
    
    leagues = users[username].get("saved_leagues", [])
    league_id = league_data.get("id") or secrets.token_hex(6)
    league_data["id"] = league_id
    
    if league_data.get("is_default"):
        for l in leagues:
            l["is_default"] = False
            
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
    
    if new_leagues and not any(l.get("is_default") for l in new_leagues):
        new_leagues[0]["is_default"] = True
        
    users[username]["saved_leagues"] = new_leagues
    save_users(users)
    return True
