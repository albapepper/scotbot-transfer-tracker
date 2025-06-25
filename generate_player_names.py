import cloudscraper
from bs4 import BeautifulSoup
import time
import re

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
        print(f"⚠
