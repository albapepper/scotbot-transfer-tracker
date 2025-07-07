from flask import Flask, request, Response, render_template
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
    def __init__(self, name: str, age: str, position: str, club: str, height: str = "Unknown", weight: str = "Unknown"):
        self.name = name
        self.age = age
        self.position = position
        self.club = club
        self.height = height
        self.weight = weight

def normalize_name(s: str) -> str:
    """Lowercase and remove accents for robust matching."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', s.lower())
        if unicodedata.category(c) != 'Mn'
    )

def load_player_data(filename: str) -> Tuple[Dict[str, List[str]], Dict[str, List[str]], Dict[str, PlayerInfo]]:
    """Load all player data in a single pass for efficiency."""
    df = pd.read_csv(filename, sep='\t', dtype=str)
    
    player_aliases: Dict[str, List[str]] = {}
    club_aliases: Dict[str, List[str]] = {}
    player_lookup: Dict[str, PlayerInfo] = {}
    
    for _, row in df.iterrows():
        if pd.isna(row.iloc[0]):
            continue
            
        name = row.iloc[0]
        age = row.iloc[1] if len(row) > 1 and not pd.isna(row.iloc[1]) else "Unknown"
        position = row.iloc[2] if len(row) > 2 and not pd.isna(row.iloc[2]) else "Unknown"
        club = row.iloc[3] if len(row) > 3 and not pd.isna(row.iloc[3]) else "Unknown"
        height = row.iloc[4] if len(row) > 4 and not pd.isna(row.iloc[4]) else "Unknown"
        weight = row.iloc[5] if len(row) > 5 and not pd.isna(row.iloc[5]) else "Unknown"
        
        # Player data
        norm_name = normalize_name(name)
        player_aliases.setdefault(norm_name, []).append(name)
        player_lookup[name.lower()] = PlayerInfo(name, age, position, club, height, weight)
        
        # Club data
        if club != "Unknown":
            norm_club = normalize_name(club)
            club_aliases.setdefault(norm_club, []).append(club)
    
    return player_aliases, club_aliases, player_lookup

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

def get_canonical_entity(user_input: str, aliases: Dict[str, List[str]]) -> Optional[str]:
    """Get canonical name for player or club."""
    norm_input = normalize_name(user_input)
    return aliases.get(norm_input, [None])[0]

# Load all data once
PLAYER_FILE = "player-position-club.txt"
player_aliases, club_aliases, PLAYER_LOOKUP = load_player_data(PLAYER_FILE)
club_aliases = add_united_aliases(club_aliases)  # Add dynamic "utd"/"united" aliases
player_automaton = build_automaton(player_aliases)
club_automaton = build_automaton(club_aliases)
@app.route("/", methods=["GET"])
def home():
    return render_template("home.html")

@app.route("/transfers", methods=["GET"])
def get_transfer_mentions():
    query = request.args.get("query", "").rstrip()
    search_type = request.args.get("type", "team")
    window = int(request.args.get("window", 24))
    
    if not query:
        return render_template("home.html", error="Missing 'query' parameter")

    # Fetch RSS feed
    try:
        rss_url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}"
        feed = feedparser.parse(rss_url)
        recent_articles = filter_recent_articles(feed.entries, hours=window)
    except Exception as e:
        return render_template("home.html", error=f"Failed to fetch news: {str(e)}")
    
    # Team search
    if search_type == "team":
        canonical_query = get_canonical_entity(query, club_aliases)
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
                        article_data = (entry.title, entry.link, entry.get("description", ""))
                        if info.club == canonical_query:
                            outgoing_mentions[player] += 1
                            outgoing_articles[player].add(article_data)
                        else:
                            incoming_mentions[player] += 1
                            incoming_articles[player].add(article_data)

        if not team_found:
            return render_template("home.html", error="No articles found for this team.")

        team_display = canonical_query.title()
        team_link = f'<a href="/team?name={urllib.parse.quote(canonical_query)}" class="results-header-link">{team_display}</a>'
        
        app.config["ENTITY_ARTICLES"] = {**incoming_articles, **outgoing_articles}
        app.config["ENTITY_TYPE"] = "players"
        
        return render_template(
            "transfers.html",
            header=f'{team_link} Transfer Results',
            incoming_mentions=list(incoming_mentions.most_common()),
            outgoing_mentions=list(outgoing_mentions.most_common()),
            player_name=None  # No player name for team searches
        )

    # Player search
    canonical_player = get_canonical_entity(query, player_aliases)
    if not canonical_player:
        return render_template("home.html", error="No articles found for this player.")
    
    club_mentions = Counter()
    player_articles = defaultdict(set)
    player_found = False
    
    for entry in recent_articles:
        text = (entry.title or "") + " " + (entry.get("description") or "")
        found_players = find_entities(text, player_automaton)
        
        if canonical_player in found_players:
            player_found = True
            # Find clubs mentioned in the same article
            found_clubs = find_entities(text, club_automaton)
            
            # Store the article for the player
            player_articles[canonical_player].add((entry.title, entry.link, entry.get("description", "")))
            
            # Count mentions for each club found in the article
            for club in found_clubs:
                club_mentions[club] += 1
    
    if not player_found:
        return render_template("home.html", error="No articles found for this player.")
    
    player_display = canonical_player.title()
    player_link = f'<a href="/player?name={urllib.parse.quote(canonical_player)}&type=players" class="results-header-link">{player_display}</a>'
    
    app.config["ENTITY_ARTICLES"] = player_articles
    app.config["ENTITY_TYPE"] = "players"
    
    # Convert club mentions to the format expected by the template
    club_mentions_list = [(club, count) for club, count in club_mentions.most_common()]
    
    return render_template(
        "transfers.html",
        header=f'{player_link} Transfer Results',
        incoming_mentions=[],  # No incoming/outgoing concept for players
        outgoing_mentions=club_mentions_list,
        player_name=canonical_player  # Pass player name for template links
    )
@app.route("/team", methods=["GET"])
def team_page():
    team_name = request.args.get("name")
    if not team_name:
        return Response("Missing team name", status=400)
    
    decoded_team = urllib.parse.unquote(team_name)
    team_players = []
    
    # Use cached player data instead of reading file
    for player_info in PLAYER_LOOKUP.values():
        if player_info.club.lower() == decoded_team.lower():
            team_players.append((player_info.name, player_info.age, player_info.position, player_info.height, player_info.weight))
    
    return render_template(
        "team.html",
        decoded_team=decoded_team,
        players=team_players
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
            club_link = f"/team?name={urllib.parse.quote(info.club)}"
            fbref_url = f"https://fbref.com/search/search.fcgi?search={urllib.parse.quote(decoded_name)}"
            club_str = (
                f"<b>Club:</b> "
                f"<a href='{club_link}' class='results-header-link' style='color:#7c31ff;text-decoration:underline;font-weight:bold;font-size:1.1rem'>{info.club}</a><br>"
                f"<b>Position:</b> {info.position}<br>"
                f"<b>Age:</b> {info.age}<br>"
                f"<b>Height:</b> {info.height}<br>"
                f"<b>Weight:</b> {info.weight}<br>"
                f"<a href='{fbref_url}' class='results-header-link' target='_blank' style='color:#7c31ff;text-decoration:underline;font-weight:bold;font-size:1.1rem'>Stats</a>"
            )
        else:
            club_str = (
                f"<b>Club:</b> Unknown<br>"
                f"<b>Position:</b> Unknown<br>"
                f"<b>Age:</b> Unknown<br>"
                f"<b>Height:</b> Unknown<br>"
                f"<b>Weight:</b> Unknown"
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
@app.route("/player-club", methods=["GET"])
def player_club_mentions():
    player_name = request.args.get("player")
    club_name = request.args.get("club")
    window = int(request.args.get("window", 24))
    
    if not player_name or not club_name:
        return Response("Missing player or club name", status=400)
    
    decoded_player = urllib.parse.unquote(player_name)
    decoded_club = urllib.parse.unquote(club_name)
    
    # Get canonical names
    canonical_player = get_canonical_entity(decoded_player, player_aliases)
    canonical_club = get_canonical_entity(decoded_club, club_aliases)
    
    if not canonical_player or not canonical_club:
        return render_template("home.html", error="Player or club not found")
    
    # Fetch RSS feed for both player and club
    try:
        search_query = f"{decoded_player} {decoded_club}"
        rss_url = f"https://news.google.com/rss/search?q={search_query.replace(' ', '+')}"
        feed = feedparser.parse(rss_url)
        recent_articles = filter_recent_articles(feed.entries, hours=window)
    except Exception as e:
        return render_template("home.html", error=f"Failed to fetch news: {str(e)}")
    
    # Find articles that mention both player and club
    matching_articles = []
    
    for entry in recent_articles:
        text = (entry.title or "") + " " + (entry.get("description") or "")
        found_players = find_entities(text, player_automaton)
        found_clubs = find_entities(text, club_automaton)
        
        if canonical_player in found_players and canonical_club in found_clubs:
            matching_articles.append((entry.title, entry.link, entry.get("description", "")))
    
    # Create header with links
    player_link = f'<a href="/player?name={urllib.parse.quote(canonical_player)}&type=players" class="results-header-link">{canonical_player.title()}</a>'
    club_link = f'<a href="/team?name={urllib.parse.quote(canonical_club)}" class="results-header-link">{canonical_club.title()}</a>'
    header = f'{player_link} × {club_link} Transfer Articles'
    
    return render_template(
        "player.html",
        decoded_name=f"{canonical_player} × {canonical_club}",
        header=header,
        club_str="",
        articles=set(matching_articles),
        entity_type="player-club"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)