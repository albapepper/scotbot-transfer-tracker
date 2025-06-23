import cloudscraper
from bs4 import BeautifulSoup

BASE_URL = "https://fbref.com"
LEAGUE_URLS = [
    "/en/comps/9/Premier-League-Stats",
    "/en/comps/12/La-Liga-Stats",
    "/en/comps/11/Serie-A-Stats",
    "/en/comps/20/Bundesliga-Stats",
    "/en/comps/13/Ligue-1-Stats"
]

scraper = cloudscraper.create_scraper()
all_players = set()

def get_player_names(league_url):
    full_url = BASE_URL + league_url
    res = scraper.get(full_url)
    print(f"🔍 Fetching {full_url} — Status: {res.status_code}")
    soup = BeautifulSoup(res.text, "html.parser")
    table = soup.find("table", {"id": "stats_standard"})
    if not table:
        print(f"⚠️  Could not find player table at {full_url}")
        return []
    players = set()
    for row in table.find_all("tr"):
        cell = row.find("td", {"data-stat": "player"})
        if cell:
            players.add(cell.text.strip())
    print(f"✅ Found {len(players)} players at {league_url}")
    return players

for url in LEAGUE_URLS:
    all_players.update(get_player_names(url))

print(f"📝 Writing {len(all_players)} players to player_names.txt")

with open("player_names.txt", "w", encoding="utf-8") as f:
    for name in sorted(all_players):
        f.write(name + "\n")
