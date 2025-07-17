import feedparser
from datetime import datetime, timedelta, timezone
from flask import Flask, request, Response, render_template, jsonify
import urllib.parse
import unicodedata
import ahocorasick
import pandas as pd
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import time
from pathlib import Path

# Utility: Render error page with message and status
def render_error(message, status=400):
    return render_template("home.html", error=message), status
# Utility: Get PlayerInfo for a canonical player name
def get_player_info(canonical_player: str) -> 'PlayerInfo|None':
    if not canonical_player:
        return None
    return PLAYER_LOOKUP.get(canonical_player.lower())
# Utility: Get all players for a given team name
def get_players_for_team(team_name: str) -> list[dict]:
    players = []
    for player_info in PLAYER_LOOKUP.values():
        if player_info.club.lower() == team_name.lower():
            players.append({
                'name': player_info.name,
                'age': player_info.age,
                'position': player_info.position,
                'nationality': player_info.nationality,
                'link': f"/transfers?query={urllib.parse.quote(player_info.name)}&type=player"
            })
    return players
def filter_articles_with_entities(articles, required_players=None, required_teams=None, player_automaton=None, club_automaton=None):
    """Return articles mentioning all required players and/or teams (by canonical name)."""
    if required_players is not None:
        required_players = set(required_players)
    if required_teams is not None:
        required_teams = set(required_teams)
    filtered = []
    seen_links = set()
    for entry in articles:
        found_players, found_teams = extract_entities(entry, player_automaton, club_automaton)
        if required_players and not required_players.issubset(found_players):
            continue
        if required_teams and not required_teams.issubset(found_teams):
            continue
        if entry.link not in seen_links:
            filtered.append((entry.title, entry.link, entry.get("description", "")))
            seen_links.add(entry.link)
    return filtered
def get_entity_mentions(articles, target_entity, entity_type, player_automaton, club_automaton, exclude=None):
    """Count unique articles mentioning both the target entity and other entities of the opposite type."""
    result = {}
    for entry in articles:
        found_players, found_teams = extract_entities(entry, player_automaton, club_automaton)
        if entity_type == 'team':
            if target_entity in found_teams:
                for player in found_players:
                    if player != target_entity:
                        result.setdefault(player, set()).add(entry.link)
        elif entity_type == 'player':
            if target_entity in found_players:
                for club in found_teams:
                    if (exclude is None) or (club != exclude):
                        result.setdefault(club, set()).add(entry.link)
    return result
def build_team_roster_context(decoded_team, team_players):
    """Context for /teams roster page."""
    context = dict(
        decoded_team=decoded_team,
        players=team_players
    )
    if not team_players:
        context["players"] = []
        context["no_mentions_message"] = "No players found for this team."
    return context
def build_transfer_link_context(canonical_player, canonical_team, matching_articles):
    """Context for /transfers/link results."""
    player_link = f'<a href="/transfers?query={urllib.parse.quote(canonical_player)}&type=player" class="results-header-link">{canonical_player.title()}</a>'
    team_link = f'<a href="/transfers?query={urllib.parse.quote(canonical_team)}&type=team" class="results-header-link">{canonical_team.title()}</a>'
    header = f'{player_link} × {team_link} Articles'
    context = dict(
        decoded_name=f"{canonical_player} × {canonical_team}",
        header=header,
        club_str="",
        articles=set(matching_articles),
        entity_type="player-club"
    )
    if not matching_articles:
        context["articles"] = set()
        context["no_mentions_message"] = "No recent articles found."
    return context
def build_player_info_block(player_info, canonical_player, show_stats_link=True):
    """Return HTML for the player info block."""
    if player_info:
        club_link = f"/transfers?query={urllib.parse.quote(player_info.club)}&type=team"
        stats_url = f"/player-stats?player={urllib.parse.quote(canonical_player)}"
        
        base_info = (
            f"<b>Club:</b> "
            f"<a href='{club_link}' class='results-header-link' style='color:#7c31ff;text-decoration:underline;font-weight:bold;font-size:1.1rem'>{player_info.club}</a><br>"
            f"<b>Position:</b> {player_info.position}<br>"
            f"<b>Age:</b> {player_info.age}<br>"
            f"<b>Nationality:</b> {player_info.nationality}"
        )
        
        if show_stats_link:
            base_info += f"<br><a href='{stats_url}' class='results-header-link' style='color:#7c31ff;text-decoration:underline;font-weight:bold;font-size:1.1rem'>Stats</a>"
        
        return base_info
    else:
        return (
            f"<b>Club:</b> Unknown<br>"
            f"<b>Position:</b> Unknown<br>"
            f"<b>Age:</b> Unknown<br>"
            f"<b>Nationality:</b> Unknown"
        )
def extract_entities(entry, player_automaton, club_automaton):
    """Return (players, teams) found in an article entry."""
    text = (entry.title or "") + " " + (entry.get("description") or "")
    found_players = find_entities(text, player_automaton)
    found_teams = find_entities(text, club_automaton)
    return found_players, found_teams
def fetch_recent_articles(query: str, hours: int = 24):
    """Fetch and filter recent RSS articles for a query."""
    rss_url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}"
    feed = feedparser.parse(rss_url)
    return filter_recent_articles(feed.entries, hours=hours)
from flask import Flask, request, Response, render_template
def build_team_context(canonical_team, mentions_list):
    """Context for team search results."""
    team_display = canonical_team.title()
    header = f'{team_display} trending mentions'
    current_roster_link = f'<a href="/teams?name={urllib.parse.quote(canonical_team)}" class="results-header-link">Current Roster</a>'
    context = dict(
        header=header,
        current_roster_link=current_roster_link,
        outgoing_mentions=mentions_list,
    )
    if not mentions_list:
        context["outgoing_mentions"] = []
        context["no_mentions_message"] = "No recent mentions."
    return context

def build_player_context(canonical_player, player_info, linked_teams, show_stats_link=True):
    """Context for player search results."""
    club_str = build_player_info_block(player_info, canonical_player, show_stats_link)
    header = f"{canonical_player.title()}"
    # Always set all keys expected by player.html
    context = dict(
        decoded_name=canonical_player,
        header=header,
        club_str=club_str,
        articles=None,
        entity_type="players",
        linked_teams=linked_teams if linked_teams else [],
        no_mentions_message="No recent mentions." if not linked_teams else None
    )
    return context

app = Flask(__name__)
@app.route("/autocomplete", methods=["GET"])
def autocomplete():
    query = request.args.get("query", "").strip().lower()
    suggestions = set()
    if query:
        # Search both players and clubs (case-insensitive, substring match)
        for norm_name, names in player_aliases.items():
            for name in names:
                if query in name.lower():
                    suggestions.add(name)
        for norm_name, names in club_aliases.items():
            for name in names:
                if query in name.lower():
                    suggestions.add(name)
    # Return up to 10 suggestions, sorted alphabetically
    return jsonify(sorted(suggestions)[:10])



# --- Data Model ---
from dataclasses import dataclass

@dataclass
class PlayerInfo:
    name: str
    age: str
    position: str
    club: str
    nationality: str = "Unknown"


# --- Utility Functions ---
def normalize_name(s: str) -> str:
    """Lowercase and remove accents for robust matching."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', s.lower())
        if unicodedata.category(c) != 'Mn'
    )

def load_player_data(filename: str) -> Tuple[Dict[str, List[str]], Dict[str, List[str]], Dict[str, PlayerInfo]]:
    player_aliases: Dict[str, List[str]] = {}
    club_aliases: Dict[str, List[str]] = {}
    player_lookup: Dict[str, PlayerInfo] = {}
    insert_re = re.compile(r"INSERT INTO player_stats VALUES \((.*?)\);", re.IGNORECASE)
    with open(filename, encoding="utf-8") as f:
        for line in f:
            match = insert_re.match(line.strip())
            if not match:
                continue
            # Split values, handling quoted strings and commas
            raw = match.group(1)
            # Remove surrounding single quotes and split on ", '"
            values = [v.strip().strip("'") for v in re.split(r",(?=(?:[^']*'[^']*')*[^']*$)", raw)]
            if len(values) < 6:
                continue
            name = values[1]
            nationality = values[2] if len(values) > 2 and values[2] else "Unknown"
            position = values[3] if values[3] else "Unknown"
            club = values[4] if values[4] else "Unknown"
            age = values[5] if values[5] else "Unknown"
            norm_name = normalize_name(name)
            player_aliases.setdefault(norm_name, []).append(name)
            player_lookup[name.lower()] = PlayerInfo(name, age, position, club, nationality)
            if club != "Unknown":
                norm_club = normalize_name(club)
                club_aliases.setdefault(norm_club, []).append(club)
    return player_aliases, club_aliases, player_lookup



# Generic alias adder for club names
def add_aliases(aliases_dict: Dict[str, List[str]], replacements: list[tuple[str, str]]) -> Dict[str, List[str]]:
    """
    Add aliases for all clubs based on a list of (old, new) substring replacements.
    """
    new_aliases: Dict[str, List[str]] = {}
    for norm_alias, canon_list in list(aliases_dict.items()):
        for old, new in replacements:
            if old in norm_alias:
                alt_alias = norm_alias.replace(old, new)
                if alt_alias not in aliases_dict:
                    new_aliases[alt_alias] = canon_list
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
DATA_DIR = Path(__file__).parent
PLAYER_FILE = DATA_DIR / "player-stats.sql"
player_aliases, club_aliases, PLAYER_LOOKUP = load_player_data(str(PLAYER_FILE))
# Add all relevant club aliases in one go
club_aliases = add_aliases(club_aliases, [
    ("utd", "united"), ("united", "utd"),
    ("manchester united", "man united"), ("man united", "manchester united"),
    ("manchester city", "man city"), ("man city", "manchester city"),
    ("man united", "man u"), ("man u", "man united"), ("manchester united", "man u"), ("man u", "manchester united"),
    ("nott'ham forest", "nottingham forest"), ("nottingham forest", "nott'ham forest")
])
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
        return render_error("Missing 'query' parameter")

    # Fetch RSS feed
    try:
        recent_articles = fetch_recent_articles(query, hours=window)
    except Exception as e:
        return render_template("home.html", error=f"Failed to fetch news: {str(e)}")

    # Unified logic for both player and team search
    canonical_team = get_canonical_entity(query, club_aliases)
    canonical_player = get_canonical_entity(query, player_aliases)

    if search_type == "team" and canonical_team:
        try:
            player_article_links = get_entity_mentions(
                recent_articles, canonical_team, 'team', player_automaton, club_automaton
            )
            mentions_list = [
                (player, len(links), f"/transfers/link?player={urllib.parse.quote(player)}&team={urllib.parse.quote(canonical_team)}")
                for player, links in sorted(player_article_links.items(), key=lambda x: len(x[1]), reverse=True)
            ]
            context = build_team_context(canonical_team, mentions_list)
            return render_template("transfers.html", **context)
        except Exception as e:
            import traceback
            print("[ERROR] /transfers team block:", traceback.format_exc())
            return render_template("home.html", error=f"Internal error: {str(e)}")
    elif canonical_player:
        try:
            player_info = get_player_info(canonical_player)
            current_club = player_info.club if player_info else None
            club_article_map = get_entity_mentions(
                recent_articles, canonical_player, 'player', player_automaton, club_automaton, exclude=current_club
            )
            linked_teams = [
                (club, len(links), f"/transfers/link?player={urllib.parse.quote(canonical_player)}&team={urllib.parse.quote(club)}")
                for club, links in sorted(club_article_map.items(), key=lambda x: len(x[1]), reverse=True)
            ]
            context = build_player_context(canonical_player, player_info, linked_teams)
            return render_template("player.html", **context)
        except Exception as e:
            import traceback
            print("[ERROR] /transfers player block:", traceback.format_exc())
            return render_template("home.html", error=f"Internal error: {str(e)}")
    return render_error("No articles found for this player or team.")
@app.route("/transfers/link", methods=["GET"])
def transfers_link():
    player = request.args.get("player")
    team = request.args.get("team")
    window = int(request.args.get("window", 24))
    if not player or not team:
        return render_error("Missing player or team parameter")
    decoded_player = urllib.parse.unquote(player)
    decoded_team = urllib.parse.unquote(team)
    canonical_player = get_canonical_entity(decoded_player, player_aliases)
    canonical_team = get_canonical_entity(decoded_team, club_aliases)
    if not canonical_player or not canonical_team:
        return render_error("Player or team not found")
    # Fetch RSS feed for both player and team
    try:
        search_query = f"{decoded_player} {decoded_team}"
        recent_articles = fetch_recent_articles(search_query, hours=window)
    except Exception as e:
        return render_error(f"Failed to fetch news: {str(e)}")
    # Find articles that mention both player and team
    # (No direct PLAYER_LOOKUP access here, but if you add it, use get_player_info)
    matching_articles = filter_articles_with_entities(
        recent_articles,
        required_players=[canonical_player],
        required_teams=[canonical_team],
        player_automaton=player_automaton,
        club_automaton=club_automaton
    )
    context = build_transfer_link_context(canonical_player, canonical_team, matching_articles)
    return render_template("player.html", **context)
@app.route("/teams", methods=["GET"])
def teams_page():
    team_name = request.args.get("name")
    if not team_name:
        return render_error("Missing team name")
    
    decoded_team = urllib.parse.unquote(team_name)
    team_players = get_players_for_team(decoded_team)
    context = build_team_roster_context(decoded_team, team_players)
    return render_template("team.html", **context)

@app.route("/player-stats", methods=["GET"])
def player_stats_page():
    player_name = request.args.get("player", "").strip()
    if not player_name:
        return render_error("Missing player parameter")
    decoded_player = urllib.parse.unquote(player_name)
    canonical_player = get_canonical_entity(decoded_player, player_aliases)
    if not canonical_player:
        return render_error("Player not found")
    # Find the full stats row for this player from the SQL file
    stats_row = None
    stat_keys = []
    sql_file = str(PLAYER_FILE)
    insert_re = re.compile(r"INSERT INTO player_stats VALUES \((.*?)\);", re.IGNORECASE)
    
    # First, get the column names from the CREATE TABLE statement
    with open(sql_file, encoding="utf-8") as f:
        content = f.read()
        # Find the CREATE TABLE statement
        create_match = re.search(r"CREATE TABLE.*?player_stats\s*\((.*?)\);", content, re.DOTALL | re.IGNORECASE)
        if create_match:
            columns_text = create_match.group(1)
            # Extract column names (everything between backticks)
            column_matches = re.findall(r"`([^`]+)`", columns_text)
            stat_keys = column_matches
    
    # Now find the player's data row
    with open(sql_file, encoding="utf-8") as f:
        for line in f:
            match = insert_re.match(line.strip())
            if not match:
                continue
            raw = match.group(1)
            values = [v.strip().strip("'") for v in re.split(r",(?=(?:[^']*'[^']*')*[^']*$)", raw)]
            if len(values) < 2:
                continue
            if values[1].lower() == canonical_player.lower():
                stats_row = values
                break
    
    # Create the stats dictionary, excluding internal fields
    player_stats = {}
    if stats_row and stat_keys and len(stats_row) == len(stat_keys):
        for i, (key, value) in enumerate(zip(stat_keys, stats_row)):
            # Skip internal/less meaningful columns
            if key not in ['Rk', 'Player', 'Nation', 'Pos', 'Squad', 'Born', 'Matches']:
                player_stats[key] = value
    
    player_info = get_player_info(canonical_player)
    linked_teams = []
    context = build_player_context(canonical_player, player_info, linked_teams, show_stats_link=False)
    context["player_stats"] = player_stats
    return render_template("player-stats.html", **context)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
