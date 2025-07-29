import requests

LEAGUE_ID = '1185263580356419584'  # Replace with your actual league ID
WEEK = 1  # You can change this to any week number


def get_users(league_id):
    url = f'https://api.sleeper.app/v1/league/{league_id}/users'
    return requests.get(url).json()


def get_rosters(league_id):
    url = f'https://api.sleeper.app/v1/league/{league_id}/rosters'
    return requests.get(url).json()


def get_matchups(league_id, week):
    url = f'https://api.sleeper.app/v1/league/{league_id}/matchups/{week}'
    return requests.get(url).json()


# Run the functions
users = get_users(LEAGUE_ID)
rosters = get_rosters(LEAGUE_ID)
matchups = get_matchups(LEAGUE_ID, WEEK)

# Display sample data
print("Users:")
for user in users:
    print("-", user['display_name'])

print("\nRosters:")
for r in rosters:
    print("-", r['owner_id'])

print(f"\nMatchups for Week {WEEK}:")
print(matchups)

def get_all_players():
    url = 'https://api.sleeper.app/v1/players/nfl'
    return requests.get(url).json()

players = get_all_players()

# Sample lookup: convert a player ID to their full name
def get_player_name(player_id):
    player = players.get(player_id, {})
    return f"{player.get('full_name', 'Unknown')} ({player.get('position', '')})"

# Example: show all players from each roster
for roster in rosters:
    owner_id = roster['owner_id']
    player_ids = roster.get('players', [])
    owner_name = next((u['display_name'] for u in users if u['user_id'] == owner_id), 'Unknown Owner')

    print(f"\n{owner_name}'s Roster:")
    for pid in player_ids:
        print(" -", get_player_name(pid))
