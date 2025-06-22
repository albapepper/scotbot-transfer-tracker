import requests

def get_players_by_club(club_id):
    url = f"https://transfermarkt-api.fly.dev/players/by-club/{club_id}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return [player["name"] for player in data.get("players", [])]
    return []

def save_player_names(player_names, filename="player_names.txt"):
    with open(filename, "w", encoding="utf-8") as f:
        for name in sorted(set(player_names)):
            f.write(name + "\n")

# Example: club IDs for top European teams
club_ids = [
    11,   # Real Madrid
    31,   # Manchester United
    27,   # Bayern Munich
    631,  # Arsenal
    44,   # Barcelona
    148,  # PSG
    148,  # PSG (duplicate safe due to set)
    46,   # Chelsea
    28,   # Borussia Dortmund
    36    # Juventus
]

all_players = []
for club_id in club_ids:
    all_players.extend(get_players_by_club(club_id))

save_player_names(all_players)
print(f"Saved {len(set(all_players))} unique player names to player_names.txt")
