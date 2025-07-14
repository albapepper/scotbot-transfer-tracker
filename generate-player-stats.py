import cloudscraper
from bs4 import BeautifulSoup
import time
import re
import os
import pandas as pd
import certifi  # Step 1: Import certifi

BASE_URL = "https://fbref.com"
LEAGUE_OVERVIEWS = {
    "Premier League": "/en/comps/9/Premier-League-Stats",
    "La Liga": "/en/comps/12/La-Liga-Stats",
    "Serie A": "/en/comps/11/Serie-A-Stats",
    "Bundesliga": "/en/comps/20/Bundesliga-Stats",
    "Ligue 1": "/en/comps/13/Ligue-1-Stats",
    "Primeira Liga": "/en/comps/32/Primeira-Liga-Stats",
    "Eredivisie": "/en/comps/23/Eredivisie-Stats",
    "Belgian Pro League": "/en/comps/37/Belgian-Pro-League-Stats",
    "Major League Soccer": "/en/comps/22/Major-League-Soccer-Stats",
    "Liga Profesional Argentina": "/en/comps/21/Liga-Profesional-Argentina-Stats",
    "Campeonato Brasileiro Série A": "/en/comps/24/Serie-A-Stats",
}

# Step 1: Set REQUESTS_CA_BUNDLE to certifi's CA bundle
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

scraper = cloudscraper.create_scraper()
all_players = []
league_summary = {}

def find_latest_stats_url(overview_url):
    full_url = BASE_URL + overview_url
    res = scraper.get(full_url, verify=certifi.where())
    soup = BeautifulSoup(res.text, "html.parser")
    link_texts = [
        "Standard Stats", "Shooting", "Passing", "Goalkeeping", "Defensive Actions", "Possession", "Playing Time"
    ]
    for link_tag in soup.find_all("a"):
        link_label = link_tag.get_text(strip=True)
        for text in link_texts:
            if text in link_label:
                return BASE_URL + link_tag["href"]
    print(f"⚠️  Could not find a stats link for {overview_url} (tried: {', '.join(link_texts)})")
    return None

def scrape_player_data(stats_url, league):
    res = scraper.get(stats_url, verify=certifi.where())  # <-- Add verify
    html = res.text
    # ...existing code...
    # Unwrap commented-out tables
    commented_html = re.findall(r'<!--(.*?)-->', html, re.DOTALL)
    for comment in commented_html:
        html = html.replace(f"<!--{comment}-->", comment)
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": "stats_standard"})
    if not table:
        print(f"⚠️  No stats table found for {league} at {stats_url}")
        return [], []
    # Get headers from thead
    headers = []
    thead = table.find("thead")
    if thead:
        header_row = thead.find_all("tr")[-1]  # Use the last header row (usually contains the column names)
        for th in header_row.find_all("th"):
            headers.append(th.get_text(strip=True))
    # Get data rows
    players = []
    for row in table.find("tbody").find_all("tr"):
        if row.get("class") and "thead" in row.get("class"):
            continue  # skip header rows inside tbody
        player_data = []
        for cell in row.find_all(["th", "td"]):
            player_data.append(cell.get_text(strip=True))
        if player_data and len(player_data) == len(headers):
            players.append(player_data)
    print(f"✅ {league}: {len(players)} players")
    league_summary[league] = len(players)
    return headers, players

all_headers = None
all_data = []
for league, overview in LEAGUE_OVERVIEWS.items():
    stats_url = find_latest_stats_url(overview)
    if stats_url:
        time.sleep(1)  # Be polite to FBref servers
        headers, players = scrape_player_data(stats_url, league)
        if all_headers is None and headers:
            all_headers = headers
        all_data.extend(players)


# Write to SQL file
output_sql = os.path.join(os.path.dirname(os.path.abspath(__file__)), "player-stats.sql")
if all_headers and all_data:
    table_name = "player_stats"
    # Create table statement
    col_defs = ',\n    '.join([f'`{col}` TEXT' for col in all_headers])
    create_stmt = f"CREATE TABLE IF NOT EXISTS {table_name} (\n    {col_defs}\n);\n"
    # Insert statements
    insert_stmts = []
    for row in all_data:
        values = []
        for val in row:
            # Escape single quotes for SQL
            if val is None:
                values.append('NULL')
            else:
                values.append("'" + str(val).replace("'", "''") + "'")
        insert_stmts.append(f"INSERT INTO {table_name} VALUES (" + ', '.join(values) + ");")
    with open(output_sql, 'w', encoding='utf-8') as f:
        f.write(create_stmt)
        for stmt in insert_stmts:
            f.write(stmt + '\n')
    print(f"✅ Wrote {len(all_data)} players to SQL file at {output_sql}.")
else:
    print("⚠️ No data to write to SQL.")

print("\n📊 Player count by league:")
for league, count in league_summary.items():
    print(f"{league}: {count}")