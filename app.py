from flask import Flask, request, Response, render_template
import feedparser
from collections import Counter
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
    """
    Add 'utd' <-> 'united' aliases for all clubs, e.g. 'man utd' <-> 'man united'.
    """
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

def add_manchester_aliases(aliases_dict: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """
    Add 'man united' <-> 'manchester united' and 'man city' <-> 'manchester city' aliases for all relevant clubs.
    """
    new_aliases: Dict[str, List[str]] = {}
    for norm_alias, canon_list in list(aliases_dict.items()):
        # Manchester United
        if 'manchester united' in norm_alias:
            man_united_alias = norm_alias.replace('manchester united', 'man united')
            if man_united_alias not in aliases_dict:
                new_aliases[man_united_alias] = canon_list
        if 'man united' in norm_alias:
            manchester_united_alias = norm_alias.replace('man united', 'manchester united')
            if manchester_united_alias not in aliases_dict:
                new_aliases[manchester_united_alias] = canon_list
        # Manchester City
        if 'manchester city' in norm_alias:
            man_city_alias = norm_alias.replace('manchester city', 'man city')
            if man_city_alias not in aliases_dict:
                new_aliases[man_city_alias] = canon_list
        if 'man city' in norm_alias:
            manchester_city_alias = norm_alias.replace('man city', 'manchester city')
            if manchester_city_alias not in aliases_dict:
                new_aliases[manchester_city_alias] = canon_list
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
club_aliases = add_united_aliases(club_aliases)
club_aliases = add_manchester_aliases(club_aliases)
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

    # Unified logic for both player and team search
    canonical_team = get_canonical_entity(query, club_aliases)
    canonical_player = get_canonical_entity(query, player_aliases)

    if search_type == "team" and canonical_team:
        # Team search: list only players not currently on the team
        mention_counter = Counter()
        team_found = False
        for entry in recent_articles:
            text = (entry.title or "") + " " + (entry.get("description") or "")
            found_teams = find_entities(text, club_automaton)
            if canonical_team in found_teams:
                team_found = True
                found_players = find_entities(text, player_automaton)
                for player in found_players:
                    info = PLAYER_LOOKUP.get(player.lower())
                    if info and info.club != canonical_team:
                        mention_counter[player] += 1
        if not team_found:
            return render_template("home.html", error="No articles found for this team.")
        team_display = canonical_team.title()
        header = f'{team_display} transfer mentions'
        current_roster_link = f'<a href="/teams?name={urllib.parse.quote(canonical_team)}" class="results-header-link">Current Roster</a>'
        mentions_list = [
            (player, count, f"/transfers/link?player={urllib.parse.quote(player)}&team={urllib.parse.quote(canonical_team)}")
            for player, count in mention_counter.most_common()
        ]
        return render_template(
            "transfers.html",
            header=header,
            current_roster_link=current_roster_link,
            outgoing_mentions=mentions_list,
        )
    elif canonical_player:
        # Player search: show player info and all linked teams (like /players page)
        mention_counter = Counter()
        player_found = False
        player_info = PLAYER_LOOKUP.get(canonical_player.lower())
        current_club = player_info.club if player_info else None
        for entry in recent_articles:
            text = (entry.title or "") + " " + (entry.get("description") or "")
            found_players = find_entities(text, player_automaton)
            if canonical_player in found_players:
                player_found = True
                found_clubs = find_entities(text, club_automaton)
                for club in found_clubs:
                    if current_club is None or club != current_club:
                        mention_counter[club] += 1
        if not player_found:
            return render_template("home.html", error="No articles found for this player.")
        # Prepare linked teams list (sorted by frequency)
        linked_teams = [
            (club, count, f"/transfers/link?player={urllib.parse.quote(canonical_player)}&team={urllib.parse.quote(club)}")
            for club, count in mention_counter.most_common()
        ]
        # Player info block
        if player_info:
            club_link = f"/transfers?query={urllib.parse.quote(player_info.club)}&type=team"
            fbref_url = f"https://fbref.com/search/search.fcgi?search={urllib.parse.quote(canonical_player)}"
            club_str = (
                f"<b>Club:</b> "
                f"<a href='{club_link}' class='results-header-link' style='color:#7c31ff;text-decoration:underline;font-weight:bold;font-size:1.1rem'>{player_info.club}</a><br>"
                f"<b>Position:</b> {player_info.position}<br>"
                f"<b>Age:</b> {player_info.age}<br>"
                f"<b>Height:</b> {player_info.height}<br>"
                f"<b>Weight:</b> {player_info.weight}<br>"
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
        header = f"{canonical_player.title()}"
        return render_template(
            "player.html",
            decoded_name=canonical_player,
            header=header,
            club_str=club_str,
            articles=None,
            entity_type="players",
            linked_teams=linked_teams
        )
    else:
        return render_template("home.html", error="No articles found for this player or team.")
@app.route("/transfers/link", methods=["GET"])
def transfers_link():
    player = request.args.get("player")
    team = request.args.get("team")
    window = int(request.args.get("window", 24))
    if not player or not team:
        return render_template("home.html", error="Missing player or team parameter")
    decoded_player = urllib.parse.unquote(player)
    decoded_team = urllib.parse.unquote(team)
    canonical_player = get_canonical_entity(decoded_player, player_aliases)
    canonical_team = get_canonical_entity(decoded_team, club_aliases)
    if not canonical_player or not canonical_team:
        return render_template("home.html", error="Player or team not found")
    # Fetch RSS feed for both player and team
    try:
        search_query = f"{decoded_player} {decoded_team}"
        rss_url = f"https://news.google.com/rss/search?q={search_query.replace(' ', '+')}"
        feed = feedparser.parse(rss_url)
        recent_articles = filter_recent_articles(feed.entries, hours=window)
    except Exception as e:
        return render_template("home.html", error=f"Failed to fetch news: {str(e)}")
    # Find articles that mention both player and team
    matching_articles = []
    for entry in recent_articles:
        text = (entry.title or "") + " " + (entry.get("description") or "")
        found_players = find_entities(text, player_automaton)
        found_teams = find_entities(text, club_automaton)
        if canonical_player in found_players and canonical_team in found_teams:
            matching_articles.append((entry.title, entry.link, entry.get("description", "")))
    # Create header with links
    player_link = f'<a href="/transfers?query={urllib.parse.quote(canonical_player)}&type=player" class="results-header-link">{canonical_player.title()}</a>'
    # Team link should go to /transfers?query=team&type=team
    team_link = f'<a href="/transfers?query={urllib.parse.quote(canonical_team)}&type=team" class="results-header-link">{canonical_team.title()}</a>'
    header = f'{player_link} × {team_link} Transfer Articles'
    return render_template(
        "player.html",
        decoded_name=f"{canonical_player} × {canonical_team}",
        header=header,
        club_str="",
        articles=set(matching_articles),
        entity_type="player-club"
    )
@app.route("/teams", methods=["GET"])
def teams_page():
    team_name = request.args.get("name")
    if not team_name:
        return Response("Missing team name", status=400)
    
    decoded_team = urllib.parse.unquote(team_name)
    team_players = []
    
    # Use cached player data instead of reading file
    for player_info in PLAYER_LOOKUP.values():
        if player_info.club.lower() == decoded_team.lower():
            team_players.append({
                'name': player_info.name,
                'age': player_info.age,
                'position': player_info.position,
                'height': player_info.height,
                'weight': player_info.weight,
                'link': f"/transfers?query={urllib.parse.quote(player_info.name)}&type=player"
            })
    
    return render_template(
        "team.html",
        decoded_team=decoded_team,
        players=team_players
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)