from flask import Flask, request, Response
import feedparser
from collections import Counter, defaultdict, namedtuple
from datetime import datetime, timedelta, timezone
import time
import re
import urllib.parse
import unicodedata
import ahocorasick

app = Flask(__name__)

PlayerInfo = namedtuple('PlayerInfo', ['name', 'position', 'club'])

def normalize_name(s):
    """Lowercase and remove accents for robust matching."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', s.lower())
        if unicodedata.category(c) != 'Mn'
    )

def load_entities(filename, col_name, col_aliases=None):
    """
    Load entities (players or clubs) from a tab-separated file.
    col_name: index of the column with canonical name.
    col_aliases: optional, index of column(s) with aliases. Can be a list.
    Returns: set of canonical names, dict of {normalized name: [canonical, ...aliases]}
    """
    entities = set()
    aliases_dict = {}
    with open(filename, encoding="utf-8") as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if i == 0:
                continue  # skip header
            parts = [p.strip() for p in line.strip().split('\t')]
            if len(parts) <= col_name:
                continue
            canon = parts[col_name]
            alias_list = [canon]
            if col_aliases:
                for idx in (col_aliases if isinstance(col_aliases, list) else [col_aliases]):
                    if idx < len(parts) and parts[idx]:
                        alias_list += [a.strip() for a in parts[idx].split(',')]
            for alias in alias_list:
                norm_alias = normalize_name(alias)
                aliases_dict.setdefault(norm_alias, []).append(canon)
            entities.add(canon)
    return entities, aliases_dict

def build_automaton(aliases_dict):
    """
    Build an Aho-Corasick automaton for entity aliases.
    """
    A = ahocorasick.Automaton()
    for norm_alias in aliases_dict:
        A.add_word(norm_alias, aliases_dict[norm_alias][0])  # Store canonical
    A.make_automaton()
    return A

def find_entities(text, automaton):
    norm_text = normalize_name(text)
    found = set()
    for end_idx, canon in automaton.iter(norm_text):
        found.add(canon)
    return found

def filter_recent_articles(entries, hours=24):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return [
        entry for entry in entries
        if hasattr(entry, 'published_parsed') and
           datetime.fromtimestamp(time.mktime(entry.published_parsed)).replace(tzinfo=timezone.utc) > cutoff
    ]

# --- Load players and clubs ---
PLAYER_FILE = "player-position-club.txt"
players, player_aliases = load_entities(PLAYER_FILE, col_name=0)
clubs, club_aliases = load_entities(PLAYER_FILE, col_name=2)
player_automaton = build_automaton(player_aliases)
club_automaton = build_automaton(club_aliases)

# For player info lookup
def build_player_lookup(filename):
    lookup = {}
    with open(filename, encoding="utf-8") as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if i == 0:
                continue
            parts = [p.strip() for p in line.strip().split('\t')]
            if len(parts) == 3:
                name, position, club = parts
                lookup[name.lower()] = PlayerInfo(name, position, club)
    return lookup

PLAYER_LOOKUP = build_player_lookup(PLAYER_FILE)

@app.route("/", methods=["GET"])
def home():
    return Response("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Transfer Tracker</title>
        <style>
            html, body {
                margin: 0;
                padding: 0;
                height: 100%;
                background-color: white;
                font-family: 'Times New Roman', serif;
                color: #000;
                display: flex;
                justify-content: center;
                align-items: center;
            }
            .container {
                text-align: center;
                background-color: white;
                padding: 2rem 3rem;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            }
            h1 {
                font-size: 2rem;
                margin-bottom: 1.5rem;
                color: #000;
            }
            input[type="text"] {
                padding: 0.6rem;
                width: 240px;
                border: 1px solid #ccc;
                border-radius: 6px;
                font-size: 1rem;
                font-family: 'Times New Roman', serif;
                color: #000;
            }
            button {
                margin-top: 1rem;
                padding: 0.6rem 1.2rem;
                font-size: 1rem;
                font-family: 'Times New Roman', serif;
                color: #fff;
                background-color: #000;
                border: none;
                border-radius: 6px;
                cursor: pointer;
            }
            button:hover {
                background-color: #333;
            }
            .search-type {
                margin: 1em 0;
            }
            label {
                font-size: 1.05rem;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Transfer Tracker</h1>
            <form action="/transfers" method="get">
                <input type="text" name="query" placeholder="e.g. Chelsea or Lionel Messi" required>
                <div class="search-type">
                    <label><input type="radio" name="type" value="team" checked> Team</label>
                    <label><input type="radio" name="type" value="player"> Player</label>
                </div>
                <button type="submit">Search</button>
            </form>
        </div>
    </body>
    </html>
    """, mimetype="text/html")

@app.route("/transfers", methods=["GET"])
def get_transfer_mentions():
    query = request.args.get("query")
    search_type = request.args.get("type", "team")
    if not query:
        return Response("Missing 'query' parameter", status=400)

    rss_url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}"
    try:
        feed = feedparser.parse(rss_url)
        recent_articles = filter_recent_articles(feed.entries)
    except Exception as e:
        return Response(f"<p>Failed to fetch news: {str(e)}</p>", mimetype="text/html")

    co_mentions = Counter()
    co_articles = defaultdict(set)

    if search_type == "team":
        # Search for all players co-occurring with the team in each article
        team_found = False
        norm_query = normalize_name(query)
        for entry in recent_articles:
            text = (entry.title or "") + " " + (entry.get("description") or "")
            found_teams = find_entities(text, club_automaton)
            if any(normalize_name(t) == norm_query for t in found_teams):
                team_found = True
                found_players = find_entities(text, player_automaton)
                for player in found_players:
                    co_mentions[player] += 1
                    co_articles[player].add((entry.title, entry.link, entry.get("description", "")))
        if not team_found:
            return Response(f"No articles found for team: {query}", status=404)
        list_type = "Players"
    else:
        # Search for all teams co-occurring with the player in each article
        player_found = False
        norm_query = normalize_name(query)
        for entry in recent_articles:
            text = (entry.title or "") + " " + (entry.get("description") or "")
            found_players = find_entities(text, player_automaton)
            if any(normalize_name(p) == norm_query for p in found_players):
                player_found = True
                found_teams = find_entities(text, club_automaton)
                for team in found_teams:
                    co_mentions[team] += 1
                    co_articles[team].add((entry.title, entry.link, entry.get("description", "")))
        if not player_found:
            return Response(f"No articles found for player: {query}", status=404)
        list_type = "Teams"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Transfer Results</title>
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                height: 100%;
                background-color: white;
                font-family: 'Times New Roman', serif;
                color: #000;
                display: flex;
                justify-content: center;
                align-items: center;
            }}
            .results-container {{
                text-align: center;
                background-color: white;
                padding: 2rem 3rem;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
                max-width: 600px;
            }}
            h2 {{
                color: #000;
            }}
            ul {{
                list-style: none;
                padding-left: 0;
            }}
            li {{
                margin-bottom: 1rem;
                font-size: 1.1rem;
                color: #000;
            }}
            a {{
                color: #000;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
                color: #333;
            }}
        </style>
    </head>
    <body>
        <div class="results-container">
            <h2>{list_type} mentioned in articles with: {query.title()}</h2>
            <ul>
    """

    if not co_mentions:
        html += f"<li>No {list_type.lower()} mentioned in the last 24 hours.</li>"
    else:
        for entity, count in co_mentions.most_common():
            encoded_name = urllib.parse.quote(entity)
            html += f'<li><a href="/entity?name={encoded_name}&type={list_type.lower()}">{entity.title()}</a> — {count} mentions</li>'

    html += """
            </ul>
        </div>
    </body>
    </html>
    """

    app.config["ENTITY_ARTICLES"] = co_articles
    app.config["ENTITY_TYPE"] = list_type.lower()
    return Response(html, mimetype="text/html")

@app.route("/entity", methods=["GET"])
def entity_detail():
    entity_name = request.args.get("name")
    entity_type = request.args.get("type")
    if not entity_name or not entity_type:
        return Response("Missing query parameters", status=400)

    decoded_name = urllib.parse.unquote(entity_name)
    articles = app.config.get("ENTITY_ARTICLES", {}).get(decoded_name, set())
    if entity_type == "players":
        info = PLAYER_LOOKUP.get(decoded_name.lower())
        club_str = (
            f"<div style='margin-bottom:1em;'><b>Club:</b> {info.club}<br><b>Position:</b> {info.position}</div>"
            if info else
            f"<div style='margin-bottom:1em;'><b>Club:</b> Unknown<br><b>Position:</b> Unknown</div>"
        )
        header = f"{decoded_name.title()} (Player)"
    else:
        club_str = ""
        header = f"{decoded_name.title()} (Team)"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{decoded_name} Mentions</title>
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                height: 100%;
                background-color: white;
                font-family: 'Times New Roman', serif;
                color: #000;
                display: flex;
                justify-content: center;
                align-items: center;
            }}
            .results-container {{
                text-align: center;
                background-color: white;
                padding: 2rem 3rem;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
                max-width: 700px;
            }}
            h2 {{
                color: #000;
            }}
            ul {{
                list-style: none;
                padding-left: 0;
                text-align: left;
            }}
            li {{
                margin-bottom: 1.5rem;
                color: #000;
            }}
            a {{
                color: #000;
                text-decoration: none;
            }}
            a.link-special, a.link-special:visited {{
                color: #0645AD;
                text-decoration: underline;
                text-transform: capitalize;
            }}
            a.link-special:hover {{
                color: #0b0080;
            }}
        </style>
    </head>
    <body>
        <div class="results-container">
            <h2>{header}</h2>
            {club_str}
            <ul>
    """
    if not articles:
        html += "<li>No articles found for this entity.</li>"
    else:
        for title, link, desc in sorted(articles):
            html += f"""
            <li>
                {title}: <a href="{link}" class="link-special" target="_blank">Link</a>
            </li>
            """

    html += """
            </ul>
        </div>
    </body>
    </html>
    """
    return Response(html, mimetype="text/html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
