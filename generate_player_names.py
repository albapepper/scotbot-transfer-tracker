import requests
from bs4 import BeautifulSoup

BASE_URL = "https://fbref.com"
LEAGUE_URLS = [
    "/en/comps/9/Premier-League-Stats",
    "/en/comps/12/La-Liga-Stats",
    "/en/comps/11/Serie-A-Stats",
    "/en/comps/20/Bundesliga-Stats",
    "/en/comps/13/Ligue-1-Stats"
]

def get_player_names(league_url):
    res = requests.get(BASE_URL + league_url)
    soup = BeautifulSoup(res.text, "html.parser")
    table = soup.find("table", {"id": "stats_standard"})
    if not table:
        return []
    players = set()
    for row in table.find_all("tr"):
        cell = row.find("td", {"data-stat": "player"})
        if cell:
            players.add(cell.text.strip())
    return players

all_players = set()
for url in LEAGUE_URLS:
    all_players.update(get_player_names(url))

with open("player_names.txt", "w", encoding="utf-8") as f:
    for name in sorted(all_players):
        f.write(name + "\n")
