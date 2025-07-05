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

def add_united_aliases(aliases_dict):
    """For each alias with 'utd', add a 'united' version and vice versa."""
    new_aliases = {}
    for norm_alias, canon_list in list(aliases_dict.items()):
        if 'utd' in norm_alias:
            # Add "united" alias
            united_alias = norm_alias.replace('utd', 'united')
            if united_alias not in aliases_dict:
                new_aliases[united_alias] = canon_list
        if 'united' in norm_alias:
            # Add "utd" alias
            utd_alias = norm_alias.replace('united', 'utd')
            if utd_alias not in aliases_dict:
                new_aliases[utd_alias] = canon_list
    aliases_dict.update(new_aliases)
    return aliases_dict

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

def get_canonical_club(user_input, club_aliases):
    # Returns the canonical club name for a user query, or None if not found
    norm_input = normalize_name(user_input)
    return club_aliases.get(norm_input, [None])[0]  # returns canonical name or None

# --- Load players and clubs ---
PLAYER_FILE = "player-position-club.txt"
players, player_aliases = load_entities(PLAYER_FILE, col_name=0)
clubs, club_aliases = load_entities(PLAYER_FILE, col_name=2)
club_aliases = add_united_aliases(club_aliases)  # Add dynamic "utd"/"united" aliases
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

    if search_type == "team":
        canonical_query = get_canonical_club(query, club_aliases)
        if not canonical_query:
            return Response(f"No matching team found for: {query}", status=404)
        incoming_mentions = Counter()
        incoming_articles = defaultdict(set)
        outgoing_mentions = Counter()
        outgoing_articles = defaultdict(set)

        team_found = False
        for entry in recent_articles:
            text = (entry.title or "") + " " + (entry.get("description") or "")
            found_teams = find_entities(text, club_automaton)
            if canonical_query in found_teams:
                team_found = True
                found_players = find_entities(text, player_automaton)
                for player in found_players:
                    # Look up player's club
                    info = PLAYER_LOOKUP.get(player.lower())
                    if info:
                        if info.club == canonical_query:
                            outgoing_mentions[player] += 1
                            outgoing_articles[player].add((entry.title, entry.link, entry.get("description", "")))
                        else:
                            incoming_mentions[player] += 1
                            incoming_articles[player].add((entry.title, entry.link, entry.get("description", "")))
        if not team_found:
            return Response(f"No articles found for team: {query}", status=404)

        # Render two columns: Incoming and Outgoing
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
                    align-items: flex-start;
                }}
                .results-container {{
                    display: flex;
                    gap: 3rem;
                    background-color: white;
                    padding: 2rem 3rem;
                    border-radius: 12px;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
                    max-width: 900px;
                    margin: 2rem auto;
                }}
                .column {{
                    flex: 1 1 50%;
                }}
                h2 {{
                    color: #000;
                    text-align: center;
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
                <div class="column">
                    <h2>Incoming</h2>
                    <ul>
        """
        if not incoming_mentions:
            html += "<li>No incoming players mentioned in the last 24 hours.</li>"
        else:
            for player, count in incoming_mentions.most_common():
                encoded_name = urllib.parse.quote(player)
                html += f'<li><a href="/entity?name={encoded_name}&type=players">{player.title()}</a> — {count} mentions</li>'
        html += """
                    </ul>
                </div>
                <div class="column">
                    <h2>Outgoing</h2>
                    <ul>
        """
        if not outgoing_mentions:
            html += "<li>No outgoing players mentioned in the last 24 hours.</li>"
        else:
            for player, count in outgoing_mentions.most_common():
                encoded_name = urllib.parse.quote(player)
                html += f'<li><a href="/entity?name={encoded_name}&type=players">{player.title()}</a> — {count} mentions</li>'
        html += """
                    </ul>
                </div>
            </div>
        </body>
        </html>
        """

        app.config["ENTITY_ARTICLES"] = {**incoming_articles, **outgoing_articles}
        app.config["ENTITY_TYPE"] = "players"
        return Response(html, mimetype="text/html")

    # Player search remains unchanged (shows co-mentioned teams)
    player_found = False
    norm_query = normalize_name(query)
    co_mentions = Counter()
    co_articles = defaultdict(set)
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
            <h2>{list_type} mentioned with {query.title()}</h2>
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
