import cloudscraper
from bs4 import BeautifulSoup
import time

BASE_URL = "https://fbref.com"
LEAGUE_OVERVIEWS = {
    "Premier League": "/en/comps/9/Premier-League-Stats",
    "La Liga": "/en/comps/12/La-Liga-Stats",
    "Serie A": "/en/comps/11/Serie-A-Stats",
    "Bundesliga": "/en/comps/20/Bundesliga-Stats",
    "Ligue 1": "/en/comps/13/Ligue-1-Stats"
}

scraper = cloudscraper.create_scraper()
all_players = set()
league_summary = {}

def find_latest_stats_url(overview_url):
    full_url = BASE_URL + overview_url
    res = scraper.get(full_url)
    soup = BeautifulSoup(res.text, "html.parser")
    link_tag = soup.find("a", string="Standard Stats")
    if link_tag:
        return BASE_URL + link_tag["href"]
    print(f"⚠️  Could not find Standard Stats link for {overview_url}")
    return None

def scrape_player_names(stats_url, league):
    res = scraper.get(stats_url)
    html = res.text.replace("<!--", "").replace("-->", "")  # Unwrap commented-out tables
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "stats_standard"})
    if not table:
        print(f"⚠️  No stats table found for {league} at {stats_url}")
        return []
    players = set()
    for row in table.find_all("tr"):
        cell = row.find("td", {"data-stat": "player"})
        if cell:
            players.add(cell.text.strip())
    print(f"✅ {league}: {len(players)} players")
    league_summary[league] = len(players)
    return players

for league, overview in LEAGUE_OVERVIEWS.items():
    stats_url = find_latest_stats_url(overview)
    if stats_url:
        time.sleep(1)  # Be polite to FBref servers
        all_players.update(scrape_player_names(stats_url, league))

print(f"\n📝 Writing {len(all_players)} total players to player_names.txt")

with open("player_names.txt", "w", encoding="utf-8") as f:
    for name in sorted(all_players):
        f.write(name + "\n")

print("\n📊 Player count by league:")
for league, count in league_summary.items():
    print(f" - {league}: {count}")
