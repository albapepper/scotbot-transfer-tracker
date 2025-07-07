from flask import Flask, request, Response, render_template, url_for
import feedparser
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import time
import urllib.parse
import unicodedata
import ahocorasick
import pandas as pd
from typing import Any, Dict, List, Optional, Set, Tuple


app = Flask(__name__)

class PlayerInfo:
    def __init__(self, name: str, position: str, club: str):
        self.name = name
        self.position = position
        self.club = club

def normalize_name(s: str) -> str:
    """Lowercase and remove accents for robust matching."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', s.lower())
        if unicodedata.category(c) != 'Mn'
    )

def load_entities(filename: str, col_name: int, col_aliases: Optional[int] = None) -> Tuple[Set[str], Dict[str, List[str]]]:
    df = pd.read_csv(filename, sep='\t', dtype=str)
    entities: Set[str] = set()
    aliases_dict: Dict[str, List[str]] = {}
    for _, row in df.iterrows():
        if pd.isna(row.iloc[col_name]):
            continue
        canon = row.iloc[col_name]
        alias_list = [canon]
        if col_aliases is not None:
            idxs = col_aliases if isinstance(col_aliases, list) else [col_aliases]
            for idx in idxs:
                if idx < len(row) and not pd.isna(row.iloc[idx]):
                    alias_list += [a.strip() for a in str(row.iloc[idx]).split(',')]
        for alias in alias_list:
            norm_alias = normalize_name(alias)
            aliases_dict.setdefault(norm_alias, []).append(canon)
        entities.add(canon)
    return entities, aliases_dict

def add_united_aliases(aliases_dict: Dict[str, List[str]]) -> Dict[str, List[str]]:
    new_aliases: Dict[str, List[str]] = {}
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

def build_automaton(aliases_dict: Dict[str, List[str]]) -> ahocorasick.Automaton:
    A = ahocorasick.Automaton()
    for norm_alias in aliases_dict:
        A.add_word(norm_alias, aliases_dict[norm_alias][0])  # Store canonical
    A.make_automaton()
    return A

def find_entities(text: str, automaton: ahocorasick.Automaton) -> Set[str]:
    norm_text = normalize_name(text)
    found: Set[str] = set()
    for _, canon in automaton.iter(norm_text):
        found.add(canon)
    return found

def filter_recent_articles(entries: List[Any], hours: int = 24) -> List[Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return [
        entry for entry in entries
        if hasattr(entry, 'published_parsed') and
           datetime.fromtimestamp(time.mktime(entry.published_parsed)).replace(tzinfo=timezone.utc) > cutoff
    ]

def get_canonical_club(user_input: str, club_aliases: Dict[str, List[str]]) -> Optional[str]:
    norm_input = normalize_name(user_input)
    return club_aliases.get(norm_input, [None])[0]  # returns canonical name or None

PLAYER_FILE = "player-position-club.txt"
players, player_aliases = load_entities(PLAYER_FILE, col_name=0)
clubs, club_aliases = load_entities(PLAYER_FILE, col_name=3)
club_aliases = add_united_aliases(club_aliases)  # Add dynamic "utd"/"united" aliases
player_automaton = build_automaton(player_aliases)
club_automaton = build_automaton(club_aliases)

def build_player_lookup(filename: str) -> Dict[str, PlayerInfo]:
    df = pd.read_csv(filename, sep='\t', dtype=str)
    lookup: Dict[str, PlayerInfo] = {}
    for _, row in df.iterrows():
        if pd.isna(row.iloc[0]):
            continue
        name = row.iloc[0]
        position = row.iloc[2] if len(row) > 2 and not pd.isna(row.iloc[2]) else "Unknown"
        club = row.iloc[3] if len(row) > 3 and not pd.isna(row.iloc[3]) else "Unknown"
        lookup[name.lower()] = PlayerInfo(name, position, club)
    return lookup

PLAYER_LOOKUP = build_player_lookup(PLAYER_FILE)
@app.route("/", methods=["GET"])
def home():
    return render_template("home.html")

@app.route("/transfers", methods=["GET"])
def get_transfer_mentions():
    query = request.args.get("query")
    if query is not None:
        query = query.rstrip()
    search_type = request.args.get("type", "team")
    window = int(request.args.get("window", 24))
    if not query:
        return render_template("home.html", error="Missing 'query' parameter")

    rss_url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}"
    try:
        feed = feedparser.parse(rss_url)
        recent_articles = filter_recent_articles(feed.entries, hours=window)
    except Exception as e:
        return render_template("home.html", error=f"Failed to fetch news: {str(e)}")
    # Team search
    if search_type == "team":
        norm_query = normalize_name(query)
        canonical_query = get_canonical_club(query, club_aliases)
        if not canonical_query:
            return render_template("home.html", error=f"No matching team found for: {query}")
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
            return render_template("home.html", error="No articles found for this team.")

        team_display = canonical_query.title()
        team_link = f'<a href="/team?name={urllib.parse.quote(canonical_query)}" class="results-header-link">{team_display}</a>'
        header = f'{team_link} Transfer Results'
        # Prepare lists for template
        incoming_list = list(incoming_mentions.most_common())
        outgoing_list = list(outgoing_mentions.most_common())
        app.config["ENTITY_ARTICLES"] = {**incoming_articles, **outgoing_articles}
        app.config["ENTITY_TYPE"] = "players"
        return render_template(
            "transfers.html",
            header=header,
            incoming_mentions=incoming_list,
            outgoing_mentions=outgoing_list
        )

    # Player search: redirect to /player?name=...&type=players
    norm_query = normalize_name(query)
    canonical_player = None
    for player in players:
        if normalize_name(player) == norm_query:
            canonical_player = player
            break
    if canonical_player:
        return Response('', status=302, headers={'Location': f'/player?name={urllib.parse.quote(canonical_player)}&type=players'})
    else:
        return render_template("home.html", error="No articles found for this player.")
@app.route("/team", methods=["GET"])
def team_page():
    team_name = request.args.get("name")
    if not team_name:
        return Response("Missing team name", status=400)
    decoded_team = urllib.parse.unquote(team_name)
    players = []
    with open(PLAYER_FILE, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i == 0:
                continue
            parts = [p.strip() for p in line.strip().split('\t')]
            if len(parts) >= 4 and parts[3].lower() == decoded_team.lower():
                name, age, position, club = parts
                players.append((name, age, position))
    return render_template(
        "team.html",
        decoded_team=decoded_team,
        players=players
    )

@app.route("/player", methods=["GET"])
def player_detail():
    entity_name = request.args.get("name")
    entity_type = request.args.get("type")
    if not entity_name or not entity_type:
        return render_template("home.html", error="Missing query parameters")

    decoded_name = urllib.parse.unquote(entity_name)
    articles = app.config.get("ENTITY_ARTICLES", {}).get(decoded_name, set())
    if entity_type == "players":
        info = PLAYER_LOOKUP.get(decoded_name.lower())
        if info:
            age = "Unknown"
            with open(PLAYER_FILE, encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i == 0:
                        continue
                    parts = [p.strip() for p in line.strip().split('\t')]
                    if len(parts) >= 2 and parts[0].lower() == info.name.lower():
                        age = parts[1]
                        break
            club_link = f"/team?name={urllib.parse.quote(info.club)}"
            fbref_url = f"https://fbref.com/search/search.fcgi?search={urllib.parse.quote(decoded_name)}"
            club_str = (
                f"<b>Club:</b> "
                f"<a href='{club_link}' class='results-header-link' style='color:#7c31ff;text-decoration:underline;font-weight:bold;font-size:1.1rem'>{info.club}</a><br>"
                f"<b>Position:</b> {info.position}<br>"
                f"<b>Age:</b> {age}<br>"
                f"<a href='{fbref_url}' class='results-header-link' target='_blank' style='color:#7c31ff;text-decoration:underline;font-weight:bold;font-size:1.1rem'>Stats</a>"
            )
        else:
            club_str = (
                f"<b>Club:</b> Unknown<br>"
                f"<b>Position:</b> Unknown<br>"
                f"<b>Age:</b> Unknown"
            )
        header = f"{decoded_name.title()}"
    else:
        club_str = ""
        header = f"{decoded_name.title()} (Team)"

    return render_template(
        "player.html",
        decoded_name=decoded_name,
        header=header,
        club_str=club_str,
        articles=articles,
        entity_type=entity_type
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)