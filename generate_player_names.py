import cloudscraper
from bs4 import BeautifulSoup
import time
import re
import os

BASE_URL = "https://fbref.com"
LEAGUE_OVERVIEWS = {
    "Premier League": "/en/comps/9/Premier-League-Stats",
    "La Liga": "/en/comps/12/La-Liga-Stats",
    "Serie A": "/en/comps/11/Serie-A-Stats",
    "Bundesliga": "/en/comps/20/Bundesliga-Stats",
    "Ligue 1": "/en/comps/13/Ligue-1-Stats"
}

scraper = cloudscraper.create_scraper()
all_players = []
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

def scrape_player_data(stats_url, league):
    res = scraper.get(stats_url)
    html = res.text
    # Unwrap commented-out tables
    commented_html = re.findall(r'<!--(.*?)-->', html, re.DOTALL)
    for comment in commented_html:
        html = html.replace(f"<!--{comment}-->", comment)
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "stats_standard"})
    if not table:
        print(f"⚠️  No stats table found for {league} at {stats_url}")
        return []
    players = []
    for row in table.find_all("tr"):
        player_cell = row.find("td", {"data-stat": "player"})
        position_cell = row.find("td", {"data-stat": "position"})
        team_cell = row.find("td", {"data-stat": "team"})
        if player_cell and position_cell and team_cell:
            player_name = player_cell.text.strip()
            position = position_cell.text.strip()
            team = team_cell.text.strip()
            players.append((player_name, position, team))
    print(f"✅ {league}: {len(players)} players")
    league_summary[league] = len(players)
    return players

for league, overview in LEAGUE_OVERVIEWS.items():
    stats_url = find_latest_stats_url(overview)
    if stats_url:
        time.sleep(1)  # Be polite to FBref servers
        all_players.extend(scrape_player_data(stats_url, league))

# Debugging: Print sample entries
print(f"\nSample entries: {all_players[:5]}")

# Write to file
output_file = "player-position-club.txt"


with open(output_file, "w", encoding="utf-8") as f:
    f.write("Player Name\tPosition\tCurrent Club\n")
    written = 0
    for player in sorted(all_players):
        if isinstance(player, tuple) and len(player) == 3 and all(isinstance(field, str) for field in player):
            f.write("\t".join(player) + "\n")
            written += 1
        else:
            print(f"⚠️ Skipping malformed entry: {player}")
    print(f"✅ Wrote {written} players to file.")

print("\n📊 Player count by league:")
for league, count in league_summary.items():
    print(f" - {league}: {count}")
