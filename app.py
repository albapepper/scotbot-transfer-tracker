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
    new_aliases = {}
    for norm_alias, canon_list in list(aliases_dict.items()):
        if 'utd' in norm_alias:
            united_alias = norm_alias.replace('utd', 'united')
            if united_alias not in aliases_dict:
                new_aliases[united_alias] = canon_list
        if 'united' in norm_alias:
            utd_alias = norm_alias.replace('united', 'utd')
            if utd_alias not in aliases_dict:
                new_aliases[utd_alias] = canon_list
    aliases_dict.update(new_aliases)
    return aliases_dict

def build_automaton(aliases_dict):
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
    norm_input = normalize_name(user_input)
    return club_aliases.get(norm_input, [None])[0]  # returns canonical name or None

# --- Load players and clubs ---
PLAYER_FILE = "player-position-club.txt"
players, player_aliases = load_entities(PLAYER_FILE, col_name=0)
clubs, club_aliases = load_entities(PLAYER_FILE, col_name=2)
club_aliases = add_united_aliases(club_aliases)  # Add dynamic "utd"/"united" aliases
player_automaton = build_automaton(player_aliases)
club_automaton = build_automaton(club_aliases)

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
        <title>The Scotbot Transfer Tracker</title>
        <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
        <style>
            html, body {
                height: 100%;
                min-height: 100vh;
                margin: 0;
                padding: 0;
                width: 100vw;
                background: #ffe3b3;
                font-family: 'Share Tech Mono', monospace;
                color: #4c2785;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
            }
            .header {
                margin-top: 3rem;
                margin-bottom: 2.5rem;
                font-size: 2.1rem;
                letter-spacing: 2px;
                color: #fff;
                background: linear-gradient(90deg, #7c31ff 30%, #a968e2 100%);
                padding: 1.5rem 2.5rem;
                text-align: center;
                border-radius: 0.18em;
                box-shadow: none;
                text-shadow: 0 2px 0 #4c2785, 0 4px 8px #0001;
                border: 0;
                font-family: 'Share Tech Mono', monospace;
            }
            .search-box {
                margin: 0 auto;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                background: none;
            }
            input[type="text"] {
                margin-bottom: 1.5rem;
                padding: 1.2rem 1rem;
                width: 350px;
                font-size: 1.1rem;
                font-family: 'Share Tech Mono', monospace;
                color: #32214a;
                background: #fffde4;
                border: none;
                border-radius: 0;
                outline: none;
                text-align: center;
            }
            .search-type, .date-range {
                margin: 1.2em 0 0.5em 0;
                color: #4c2785;
                font-size: 0.9rem;
            }
            label {
                font-size: 0.98rem;
                margin-right: 1.5em;
                cursor: pointer;
                font-family: 'Share Tech Mono', monospace;
            }
            button {
                font-family: 'Share Tech Mono', monospace;
                font-size: 1rem;
                padding: 0.8rem 2.5rem;
                background: #7c31ff;
                color: #fff;
                border: none;
                border-radius: 0;
                cursor: pointer;
                margin-top: 1rem;
                transition: background 0.2s;
            }
            button:hover {
                background: #a968e2;
            }
            .date-range select {
                font-family: 'Share Tech Mono', monospace;
                font-size: 0.85rem;
                color: #4c2785;
                background: #fffde4;
                border: none;
                border-radius: 0;
                padding: 0.3em 1em;
                margin-left: 0.5em;
                outline: none;
            }
        </style>
    </head>
    <body>
        <div class="header">The Scotbot Transfer Tracker</div>
        <form class="search-box" action="/transfers" method="get">
            <input type="text" name="query" placeholder="e.g. Chelsea or Lionel Messi" required>
            <div class="search-type">
                <label><input type="radio" name="type" value="team" checked> Team</label>
                <label><input type="radio" name="type" value="player"> Player</label>
            </div>
            <div class="date-range">
                <label>Time Window:
                    <select name="window">
                        <option value="24" selected>Last 24 hours</option>
                        <option value="72">Last 3 days</option>
                        <option value="168">Last 7 days</option>
                    </select>
                </label>
            </div>
            <button type="submit">Search</button>
        </form>
    </body>
    </html>
    """, mimetype="text/html")

@app.route("/transfers", methods=["GET"])
def get_transfer_mentions():
    query = request.args.get("query")
    search_type = request.args.get("type", "team")
    window = int(request.args.get("window", 24))
    if not query:
        return Response("Missing 'query' parameter", status=400)

    rss_url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}"
    try:
        feed = feedparser.parse(rss_url)
        recent_articles = filter_recent_articles(feed.entries, hours=window)
    except Exception as e:
        return Response(f"<p>Failed to fetch news: {str(e)}</p>", mimetype="text/html")

    # Team search
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

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Transfer Results</title>
            <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
            <style>
                html, body {{
                    margin: 0;
                    padding: 0;
                    min-height: 100vh;
                    width: 100vw;
                    background: #ffe3b3;
                    font-family: 'Share Tech Mono', monospace;
                    color: #4c2785;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                }}
                .results-header {{
                    margin-top: 2.5rem;
                    margin-bottom: 1.5rem;
                    font-size: 1.6rem;
                    color: #fff;
                    background: linear-gradient(90deg, #7c31ff 30%, #a968e2 100%);
                    padding: 1rem 2.5rem;
                    text-align: center;
                    border-radius: 0.18em;
                    text-shadow: 0 2px 0 #4c2785, 0 4px 8px #0001;
                }}
                .results-container {{
                    display: flex;
                    flex-direction: row;
                    gap: 4vw;
                    justify-content: center;
                    align-items: flex-start;
                    background: none;
                    margin-bottom: 2rem;
                    width: 100vw;
                }}
                .column {{
                    flex: 1 1 45%;
                    min-width: 270px;
                    text-align: center;
                }}
                h2 {{
                    color: #a968e2;
                    font-size: 1.1rem;
                    margin-bottom: 1.5rem;
                    margin-top: 0;
                    letter-spacing: 1px;
                }}
                ul {{
                    list-style: none;
                    padding-left: 0;
                    text-align: center;
                }}
                li {{
                    margin-bottom: 1.1rem;
                    font-size: 0.98rem;
                    color: #4c2785;
                }}
                a {{
                    color: #7c31ff;
                    text-decoration: underline;
                    transition: color 0.15s;
                }}
                a:hover {{
                    color: #a968e2;
                }}
                @media (max-width: 800px) {{
                    .results-container {{
                        flex-direction: column;
                        align-items: center;
                    }}
                    .column {{
                        min-width: 0;
                        width: 90vw;
                    }}
                    .results-header {{
                        font-size: 1.1rem;
                        padding: 0.6rem 1.1rem;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="results-header">Transfer Results</div>
            <div class="results-container">
                <div class="column">
                    <h2>Incoming</h2>
                    <ul>
        """
        if not incoming_mentions:
            html += "<li>No incoming players mentioned in the selected window.</li>"
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
            html += "<li>No outgoing players mentioned in the selected window.</li>"
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

    # Player search (co-mentioned teams)
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
        <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                min-height: 100vh;
                width: 100vw;
                background: #ffe3b3;
                font-family: 'Share Tech Mono', monospace;
                color: #4c2785;
                display: flex;
                flex-direction: column;
                align-items: center;
            }}
            .results-header {{
                margin-top: 2.5rem;
                margin-bottom: 1.5rem;
                font-size: 1.6rem;
                color: #fff;
                background: linear-gradient(90deg, #7c31ff 30%, #a968e2 100%);
                padding: 1rem 2.5rem;
                text-align: center;
                border-radius: 0.18em;
                text-shadow: 0 2px 0 #4c2785, 0 4px 8px #0001;
            }}
            .results-container {{
                text-align: center;
                background: none;
                padding: 0;
                margin-bottom: 2rem;
                max-width: 700px;
                width: 96vw;
            }}
            h2 {{
                color: #a968e2;
                font-size: 1.1rem;
                margin-bottom: 1.2rem;
                margin-top: 0;
                letter-spacing: 1px;
            }}
            ul {{
                list-style: none;
                padding-left: 0;
                text-align: center;
            }}
            li {{
                margin-bottom: 1.2rem;
                font-size: 0.95rem;
                color: #4c2785;
            }}
            a {{
                color: #7c31ff;
                text-decoration: underline;
                transition: color 0.15s;
            }}
            a:hover {{
                color: #a968e2;
            }}
        </style>
    </head>
    <body>
        <div class="results-header">{list_type} mentioned with {query.title()}</div>
        <div class="results-container">
            <ul>
    """

    if not co_mentions:
        html += f"<li>No {list_type.lower()} mentioned in the selected window.</li>"
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
            f"<div class='club-info'><b>Club:</b> {info.club}<br><b>Position:</b> {info.position}</div>"
            if info else
            f"<div class='club-info'><b>Club:</b> Unknown<br><b>Position:</b> Unknown</div>"
        )
        fbref_url = f"https://fbref.com/search/search.fcgi?search={urllib.parse.quote(decoded_name)}"
        header = f'''{decoded_name.title()} (<a href="{fbref_url}" class="stats-link" target="_blank">Stats</a>)'''
    else:
        club_str = ""
        header = f"{decoded_name.title()} (Team)"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{decoded_name} Mentions</title>
        <link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap" rel="stylesheet">
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                min-height: 100vh;
                width: 100vw;
                background: #ffe3b3;
                font-family: 'Share Tech Mono', monospace;
                color: #4c2785;
                display: flex;
                flex-direction: column;
                align-items: center;
            }}
            .results-header {{
                margin-top: 2.5rem;
                margin-bottom: 1.2rem;
                font-size: 1.1rem;
                color: #fff;
                background: linear-gradient(90deg, #7c31ff 30%, #a968e2 100%);
                padding: 0.7rem 2rem;
                text-align: center;
                border-radius: 0.18em;
                text-shadow: 0 2px 0 #4c2785, 0 4px 8px #0001;
            }}
            .results-container {{
                text-align: center;
                background: none;
                padding: 0;
                margin-bottom: 2rem;
                max-width: 700px;
                width: 96vw;
            }}
            h2 {{
                color: #a968e2;
                font-size: 1.1rem;
                margin-bottom: 1.2rem;
                margin-top: 0;
                letter-spacing: 1px;
            }}
            ul {{
                list-style: none;
                padding-left: 0;
                text-align: center;
            }}
            li {{
                margin-bottom: 1.2rem;
                font-size: 0.95rem;
                color: #4c2785;
            }}
            a {{
                color: #7c31ff;
                text-decoration: underline;
                transition: color 0.15s;
            }}
            a:hover {{
                color: #a968e2;
            }}
            .club-info {{
                margin-bottom: 1em;
                color: #4c2785;
                font-size: 0.9rem;
            }}
        </style>
    </head>
    <body>
        <div class="results-header">{header}</div>
        <div class="results-container">
            {club_str}
            <ul>
    """
    if not articles:
        html += "<li>No articles found for this entity.</li>"
    else:
        for title, link, desc in sorted(articles):
            html += f"""
            <li>
                {title}: <a href="{link}" target="_blank">Link</a>
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