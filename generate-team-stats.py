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

# For team stats
all_teams = []
team_league_summary = {}
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


# Scrape team stats from league overview page
def scrape_team_data(overview_url, league):
    full_url = BASE_URL + overview_url
    res = scraper.get(full_url, verify=certifi.where())
    html = res.text
    # Unwrap commented-out tables
    commented_html = re.findall(r'<!--(.*?)-->', html, re.DOTALL)
    for comment in commented_html:
        html = html.replace(f"<!--{comment}-->", comment)
    soup = BeautifulSoup(html, "html.parser")
    # Try to find the team stats table (usually id="stats_squads_standard_for")
    table = soup.find("table", {"id": re.compile(r"stats_squads_standard.*")})
    if not table:
        print(f"⚠️  No team stats table found for {league} at {full_url}")
        return [], []
    headers = []
    thead = table.find("thead")
    if thead:
        header_row = thead.find_all("tr")[-1]
        for th in header_row.find_all("th"):
            headers.append(th.get_text(strip=True))
    teams = []
    for row in table.find("tbody").find_all("tr"):
        if row.get("class") and "thead" in row.get("class"):
            continue
        team_data = []
        for cell in row.find_all(["th", "td"]):
            team_data.append(cell.get_text(strip=True))
        if team_data and len(team_data) == len(headers):
            teams.append(team_data)
    print(f"✅ {league}: {len(teams)} teams")
    team_league_summary[league] = len(teams)
    # Add league and country columns
    country = league_country_map.get(league, "Unknown")
    league_col = [league] * len(teams)
    country_col = [country] * len(teams)
    # Insert league and country as first columns if not present
    if 'League' not in headers:
        headers = ['League', 'Country'] + headers
        for i, row in enumerate(teams):
            teams[i] = [league, country] + row
    return headers, teams


# Map league to country (add more as needed)
league_country_map = {
    "Premier League": "England",
    "La Liga": "Spain",
    "Serie A": "Italy",
    "Bundesliga": "Germany",
    "Ligue 1": "France",
    "Primeira Liga": "Portugal",
    "Eredivisie": "Netherlands",
    "Belgian Pro League": "Belgium",
    "Major League Soccer": "USA",
    "Liga Profesional Argentina": "Argentina",
    "Campeonato Brasileiro Série A": "Brazil",
}

# Scrape and write team stats
team_headers = None
team_data = []
for league, overview in LEAGUE_OVERVIEWS.items():
    headers, teams = scrape_team_data(overview, league)
    if team_headers is None and headers:
        team_headers = headers
    team_data.extend(teams)

output_sql = os.path.join(os.path.dirname(os.path.abspath(__file__)), "team-stats.sql")
if team_headers and team_data:
    table_name = "team_stats"
    col_defs = ',\n    '.join([f'`{col}` TEXT' for col in team_headers])
    create_stmt = f"CREATE TABLE IF NOT EXISTS {table_name} (\n    {col_defs}\n);\n"
    insert_stmts = []
    for row in team_data:
        values = []
        for val in row:
            if val is None:
                values.append('NULL')
            else:
                values.append("'" + str(val).replace("'", "''") + "'")
        insert_stmts.append(f"INSERT INTO {table_name} VALUES (" + ', '.join(values) + ");")
    with open(output_sql, 'w', encoding='utf-8') as f:
        f.write(create_stmt)
        for stmt in insert_stmts:
            f.write(stmt + '\n')
    print(f"✅ Wrote {len(team_data)} teams to SQL file at {output_sql}.")
else:
    print("⚠️ No team data to write to SQL.")

print("\n📊 Team count by league:")
for league, count in team_league_summary.items():
    print(f"{league}: {count}")

print("\n📊 Player count by league:")
for league, count in league_summary.items():
    print(f"{league}: {count}")