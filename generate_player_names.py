import requests
import time

BASE_URL = "https://transfermarkt-api.fly.dev"

def get_all_clubs():
    url = f"{BASE_URL}/clubs"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json().get("clubs", [])
    return []

def get_players_by_club(club_id):
    url = f"{BASE_URL}/players/by-club/{club_id}"
    response = requests.get(url)
    if response.status_code == 200:
        return [player["name"] for player in response.json().get("players", [])]
    return []

def save_player_names(player_names, filename="player_names.txt"):
    with open(filename, "w", encoding="utf-8") as f:
        for name in sorted(set(player_names)):
            f.write(name + "\n")

def main():
    all_players = []
    clubs = get_all_clubs()
    print(f"Found {len(clubs)} clubs. Fetching players...")

    for i, club in enumerate(clubs, 1):
        club_id = club.get("id")
        club_name = club.get("name")
        if not club_id:
            continue
        try:
            players = get_players_by_club(club_id)
            all_players.extend(players)
            print(f"[{i}/{len(clubs)}] {club_name}: {len(players)} players")
            time.sleep(0.5)  # Be kind to the API
        except Exception as e:
            print(f"⚠️ Failed to fetch players for {club_name}: {e}")

    save_player_names(all_players)
    print(f"\n✅ Saved {len(set(all_players))} unique player names to player_names.txt")

if __name__ == "__main__":
    main()
