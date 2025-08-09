# --- Imports ---
import feedparser
from datetime import datetime, timedelta, timezone
from flask import Flask, request, render_template, jsonify
import urllib.parse
import unicodedata
import ahocorasick
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import time
from pathlib import Path
from dataclasses import dataclass
from api_client import api_client

# --- Flask App Setup ---
app = Flask(__name__)

# --- Routes ---
@app.route("/", methods=["GET"])
def home():
    return render_template("home.html")

@app.route("/autocomplete", methods=["GET"])
def autocomplete():
    query = request.args.get("query", "").strip().lower()
    suggestions = api_client.autocomplete(query)
    return jsonify(suggestions)

@app.route("/transfers", methods=["GET"])
def get_transfer_mentions():
    query = request.args.get("query", "").rstrip()
    search_type = request.args.get("type", "auto")  # Auto-detect by default
    window = 48  # Standardized 48 hour window

    if not query:
        return render_error("Missing 'query' parameter")

    try:
        recent_articles = fetch_recent_articles(query, hours=window)
    except Exception as e:
        return render_template("home.html", error=f"Failed to fetch news: {str(e)}")

    # Get aliases from API
    aliases_data = api_client.get_aliases()
    if not aliases_data:
        return render_template("home.html", error="Failed to load player/team data")
    
    player_aliases = aliases_data.get("player_aliases", {})
    club_aliases = aliases_data.get("club_aliases", {})

    canonical_team = get_canonical_entity(query, club_aliases)
    canonical_player = get_canonical_entity(query, player_aliases)

    # Auto-detect search type if not specified
    if search_type == "auto":
        if canonical_player:
            search_type = "player"
        elif canonical_team:
            search_type = "team"
        else:
            search_type = "player"  # Default to player when nothing found

    # Build automatons for entity extraction
    player_automaton = build_automaton(player_aliases)
    club_automaton = build_automaton(club_aliases)

    if search_type == "team":
        if canonical_team:
            try:
                player_article_links = get_entity_mentions(
                    recent_articles, canonical_team, 'team', player_automaton, club_automaton
                )
                mentions_list = [
                    (player, len(links), f"/transfers/link?player={urllib.parse.quote(player)}&team={urllib.parse.quote(canonical_team)}")
                    for player, links in sorted(player_article_links.items(), key=lambda x: len(x[1]), reverse=True)
                ]
                context = build_team_context(canonical_team, mentions_list)
                return render_template("team.html", **context)
            except Exception as e:
                import traceback
                print("[ERROR] /transfers team block:", traceback.format_exc())
                return render_template("home.html", error=f"Internal error: {str(e)}")
        else:
            # Team not found, but still show team template with no results
            context = build_team_context_for_unknown(query)
            return render_template("team.html", **context)
    else:  # search_type == "player" or anything else defaults to player
        if canonical_player:
            try:
                player_info_data = api_client.get_player_info(canonical_player)
                player_info = None
                current_club = None
                if player_info_data:
                    player_info = PlayerInfo(
                        name=player_info_data.get("name", ""),
                        born=player_info_data.get("born", ""),
                        position=player_info_data.get("position", ""),
                        club=player_info_data.get("club", ""),
                        nationality=player_info_data.get("nationality", "")
                    )
                    current_club = player_info.club
                
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
        else:
            # Player not found, show player template with no results
            context = build_player_context_for_unknown(query)
            return render_template("player.html", **context)

@app.route("/transfers/link", methods=["GET"])
def transfers_link():
    player = request.args.get("player")
    team = request.args.get("team")
    window = 48  # Standardized 48 hour window
    if not player or not team:
        return render_error("Missing player or team parameter")
    
    decoded_player = urllib.parse.unquote(player)
    decoded_team = urllib.parse.unquote(team)
    
    # Get aliases from API
    aliases_data = api_client.get_aliases()
    if not aliases_data:
        return render_error("Failed to load player/team data")
    
    player_aliases = aliases_data.get("player_aliases", {})
    club_aliases = aliases_data.get("club_aliases", {})
    
    canonical_player = get_canonical_entity(decoded_player, player_aliases)
    canonical_team = get_canonical_entity(decoded_team, club_aliases)
    
    if not canonical_player or not canonical_team:
        return render_error("Player or team not found")
    
    try:
        search_query = f"{decoded_player} {decoded_team}"
        recent_articles = fetch_recent_articles(search_query, hours=window)
    except Exception as e:
        return render_error(f"Failed to fetch news: {str(e)}")
    
    # Build automatons for entity extraction
    player_automaton = build_automaton(player_aliases)
    club_automaton = build_automaton(club_aliases)
    
    matching_articles = filter_articles_with_entities(
        recent_articles,
        required_players=[canonical_player],
        required_teams=[canonical_team],
        player_automaton=player_automaton,
        club_automaton=club_automaton
    )
    context = build_transfer_link_context(canonical_player, canonical_team, matching_articles)
    return render_template("player.html", **context)

@app.route("/team-stats", methods=["GET"])
def team_stats_page():
    team_name = request.args.get("name")
    if not team_name:
        return render_error("Missing team name")
    
    decoded_team = urllib.parse.unquote(team_name)
    
    # Get team data from API
    team_data = api_client.get_team_stats(decoded_team)
    if not team_data:
        return render_error("Team not found")
    
    # Extract data
    team_info_dict = team_data.get("team_info")
    team_stats = team_data.get("stats")
    roster_data = team_data.get("roster", [])
    
    # Convert roster to expected format
    team_players = []
    for player in roster_data:
        age = calculate_age_from_birth_year(player.get("born", ""))
        nationality_full = convert_nationality_to_full_name(player.get("nationality", ""))
        team_players.append({
            'name': player.get("name", ""),
            'born': player.get("born", ""),
            'age': age,
            'position': player.get("position", ""),
            'nationality': nationality_full,
            'link': f"/transfers?query={urllib.parse.quote(player.get('name', ''))}&type=player"
        })
    
    # Convert team info
    team_info = None
    if team_info_dict:
        team_info = TeamInfo(
            name=team_info_dict.get("name", ""),
            league=team_info_dict.get("league", ""),
            country=team_info_dict.get("country", "")
        )
    
    context = build_team_roster_context(decoded_team, team_players)
    context["team_info"] = team_info
    context["team_stats"] = team_stats
    return render_template("team-stats.html", **context)

@app.route("/player-stats", methods=["GET"])
def player_stats_page():
    player_name = request.args.get("player", "").strip()
    if not player_name:
        return render_error("Missing player parameter")
    
    decoded_player = urllib.parse.unquote(player_name)
    
    # Get player data from API
    player_data = api_client.get_player_stats(decoded_player)
    if not player_data:
        return render_error("Player not found")
    
    # Extract data
    player_info_dict = player_data.get("player_info")
    player_stats = player_data.get("stats", {})
    
    # Convert player info
    player_info = None
    if player_info_dict:
        player_info = PlayerInfo(
            name=player_info_dict.get("name", ""),
            born=player_info_dict.get("born", ""),
            position=player_info_dict.get("position", ""),
            club=player_info_dict.get("club", ""),
            nationality=player_info_dict.get("nationality", "")
        )
    
    linked_teams = []
    context = build_player_context(decoded_player, player_info, linked_teams, show_stats_link=False)
    context["player_stats"] = player_stats
    return render_template("player-stats.html", **context)

# --- Data Loading and Helper Functions ---
@dataclass
class PlayerInfo:
    name: str
    born: str
    position: str
    club: str
    nationality: str

@dataclass
class TeamInfo:
    name: str
    league: str
    country: str
    current_roster: str = ""

def render_error(message, status=400):
    return render_template("home.html", error=message), status

def filter_articles_with_entities(articles, required_players=None, required_teams=None, player_automaton=None, club_automaton=None):
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
    context = dict(
        decoded_team=decoded_team,
        players=team_players
    )
    if not team_players:
        context["players"] = []
        context["no_mentions_message"] = "No players found for this team."
    return context

def build_transfer_link_context(canonical_player, canonical_team, matching_articles):
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
    return context

def build_player_info_block(player_info, canonical_player, show_stats_link=True):
    if player_info:
        club_link = f"/transfers?query={urllib.parse.quote(player_info.club)}&type=team"
        stats_url = f"/player-stats?player={urllib.parse.quote(canonical_player)}"
        age = calculate_age_from_birth_year(player_info.born)
        nationality_full = convert_nationality_to_full_name(player_info.nationality)
        base_info = (
            f"<b>Club:</b> "
            f"<a href='{club_link}' class='results-header-link' style='color:#7c31ff;text-decoration:underline;font-weight:bold;font-size:1.1rem'>{player_info.club}</a><br>"
            f"<b>Position:</b> {player_info.position}<br>"
            f"<b>Age:</b> {age}<br>"
            f"<b>Born:</b> {player_info.born}<br>"
            f"<b>Nationality:</b> {nationality_full}"
        )
        if show_stats_link:
            base_info += f"<br><a href='{stats_url}' class='results-header-link' style='color:#7c31ff;text-decoration:underline;font-weight:bold;font-size:1.1rem'>Stats</a>"
        return base_info
    else:
        return (
            f"<b>Club:</b> Unknown<br>"
            f"<b>Position:</b> Unknown<br>"
            f"<b>Age:</b> Unknown<br>"
            f"<b>Born:</b> Unknown<br>"
            f"<b>Nationality:</b> Unknown"
        )

def extract_entities(entry, player_automaton, club_automaton):
    text = (entry.title or "") + " " + (entry.get("description") or "")
    found_players = find_entities(text, player_automaton)
    found_teams = find_entities(text, club_automaton)
    return found_players, found_teams

def fetch_recent_articles(query: str, hours: int = 24):
    rss_url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}"
    feed = feedparser.parse(rss_url)
    return filter_recent_articles(feed.entries, hours=hours)

def build_team_context(canonical_team, mentions_list):
    header = f'{canonical_team.title()} trending mentions'
    current_roster_link = f'<a href="/team-stats?name={urllib.parse.quote(canonical_team)}" class="results-header-link">Current Roster</a>'
    # Get TeamInfo
    team_info = get_team_info(canonical_team)
    context = dict(
        decoded_team=canonical_team,
        header=header,
        current_roster_link=current_roster_link,
        outgoing_mentions=mentions_list,
        team_info=team_info,
    )
    if not mentions_list:
        context["outgoing_mentions"] = []
        context["no_mentions_message"] = "No recent mentions."
    return context

def get_team_info(canonical_team: str) -> 'TeamInfo|None':
    """Get team info from API"""
    team_data = api_client.get_team_info(canonical_team)
    if not team_data:
        return None
    
    return TeamInfo(
        name=team_data.get("name", ""),
        league=team_data.get("league", ""),
        country=team_data.get("country", "")
    )

def build_player_context(canonical_player, player_info, linked_teams, show_stats_link=True):
    club_str = build_player_info_block(player_info, canonical_player, show_stats_link)
    header = f"{canonical_player.title()}"
    context = dict(
        decoded_name=canonical_player,
        header=header,
        club_str=club_str,
        articles=None,
        entity_type="players",
        linked_teams=linked_teams or [],
        no_mentions_message="No recent mentions" if not linked_teams else None
    )
    return context

def build_team_context_for_unknown(query):
    """Build team context for unknown/not found teams"""
    header = f'{query.title()} trending mentions'
    
    # Try to get team info even for "unknown" teams
    team_info = get_team_info(query)
    
    # Build current roster link if we have team info
    current_roster_link = None
    if team_info:
        current_roster_link = f'<a href="/team-stats?name={urllib.parse.quote(query)}" class="results-header-link">Current Roster</a>'
    
    context = dict(
        decoded_team=query,
        header=header,
        current_roster_link=current_roster_link,
        outgoing_mentions=[],
        team_info=team_info,
        no_mentions_message="No recent mentions found"
    )
    return context

def build_player_context_for_unknown(query):
    """Build player context for unknown/not found players"""
    header = f"{query.title()}"
    context = dict(
        decoded_name=query,
        header=header,
        club_str="",
        articles=None,
        entity_type="players",
        linked_teams=[],
        no_mentions_message="No recent mentions found"
    )
    return context

def normalize_name(s: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFD', s.lower())
        if unicodedata.category(c) != 'Mn'
    )

def convert_nationality_to_full_name(nationality_code: str) -> str:
    """Convert nationality codes like 'esESP' to full country names like 'Spanish'"""
    nationality_mapping = {
        'esESP': 'Spanish',
        'engENG': 'English', 
        'frFRA': 'French',
        'deGER': 'German',
        'itITA': 'Italian',
        'nlNED': 'Dutch',
        'ptPOR': 'Portuguese',
        'brBRA': 'Brazilian',
        'arARG': 'Argentinian',
        'uyURU': 'Uruguayan',
        'plPOL': 'Polish',
        'dkDEN': 'Danish',
        'seSWE': 'Swedish',
        'noNOR': 'Norwegian',
        'chSUI': 'Swiss',
        'atAUT': 'Austrian',
        'beRBEL': 'Belgian',
        'czCZE': 'Czech',
        'hrCRO': 'Croatian',
        'rsSRB': 'Serbian',
        'skSVK': 'Slovakian',
        'siSVN': 'Slovenian',
        'huHUN': 'Hungarian',
        'roROU': 'Romanian',
        'bgBUL': 'Bulgarian',
        'grGRE': 'Greek',
        'trTUR': 'Turkish',
        'ruRUS': 'Russian',
        'uaUKR': 'Ukrainian',
        'rsRSA': 'South African',
        'ngNGA': 'Nigerian',
        'ghGHA': 'Ghanaian',
        'ciCIV': 'Ivorian',
        'snSEN': 'Senegalese',
        'mlMLI': 'Malian',
        'cmCMR': 'Cameroonian',
        'egEGY': 'Egyptian',
        'maMAR': 'Moroccan',
        'dzALG': 'Algerian',
        'tnTUN': 'Tunisian',
        'usUSA': 'American',
        'caRCAN': 'Canadian',
        'mxMEX': 'Mexican',
        'jmJAM': 'Jamaican',
        'coRCOL': 'Colombian',
        'clCHI': 'Chilean',
        'ecECU': 'Ecuadorian',
        'pePER': 'Peruvian',
        'pyPAR': 'Paraguayan',
        'veVEN': 'Venezuelan',
        'boRBOL': 'Bolivian',
        'jpJPN': 'Japanese',
        'krKOR': 'South Korean',
        'cnCHN': 'Chinese',
        'auAUS': 'Australian',
        'nzNZL': 'New Zealand',
        'inIND': 'Indian',
        'pkPAK': 'Pakistani',
        'irIRN': 'Iranian',
        'iqIRQ': 'Iraqi',
        'saKSA': 'Saudi Arabian',
        'qatQAT': 'Qatari',
        'aeUAE': 'Emirati',
        'gwGNB': 'Guinea-Bissauan',
        'gvCPV': 'Cape Verdean',
        'aoANG': 'Angolan',
        'mzMOZ': 'Mozambican',
        'stSTP': 'São Toméan',
        'isISL': 'Icelandic',
        'fiRFIN': 'Finnish',
        'eeEST': 'Estonian',
        'lvLAT': 'Latvian',
        'ltLTU': 'Lithuanian',
        'mdMDA': 'Moldovan',
        'byBLR': 'Belarusian',
        'mkMKD': 'North Macedonian',
        'alALB': 'Albanian',
        'meRMNE': 'Montenegrin',
        'baRBIH': 'Bosnian',
        'xkKOS': 'Kosovar',
        'cyRCYP': 'Cypriot',
        'mtMLT': 'Maltese',
        'luLUX': 'Luxembourgish',
        'liLIE': 'Liechtensteiner',
        'mcRMON': 'Monégasque',
        'smRSMR': 'Sammarinese',
        'vaVAT': 'Vatican',
        'adAND': 'Andorran',
        'caCAN': 'Canadian',
        'glGIB': 'Gibraltar',
        'beBEL': 'Belgian',
        'liLIE': 'Liechtenstein',
        'foFRO': 'Faroe Islands',
        'isISL': 'Icelandic',
        'jeJEY': 'Jersey',
        'ggGGY': 'Guernsey',
    }
    
    return nationality_mapping.get(nationality_code, nationality_code if nationality_code else 'Unknown')

def calculate_age_from_birth_year(birth_year: str) -> str:
    """Calculate age from birth year string, handling various formats"""
    if not birth_year or birth_year == "Unknown":
        return "Unknown"
    
    try:
        # Handle cases where birth_year might be just a year or have other formats
        birth_year_clean = birth_year.strip()
        if birth_year_clean.isdigit() and len(birth_year_clean) == 4:
            birth_year_int = int(birth_year_clean)
            current_year = datetime.now().year
            age = current_year - birth_year_int
            return str(age)
        else:
            return "Unknown"
    except (ValueError, TypeError):
        return "Unknown"

def add_aliases(aliases_dict: Dict[str, List[str]], replacements: list[tuple[str, str]]) -> Dict[str, List[str]]:
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
        # Store both the canonical name and the alias length for boundary checking
        A.add_word(norm_alias, (aliases_dict[norm_alias][0], len(norm_alias)))
    A.make_automaton()
    return A

def find_entities(text: str, automaton: ahocorasick.Automaton) -> Set[str]:
    norm_text = normalize_name(text)
    raw_matches: List[Tuple[int, int, str, int]] = []  # (start, end, canon, length)
    for end_index, (canon, alias_length) in automaton.iter(norm_text):
        start_index = end_index - alias_length + 1
        # Require word boundaries for every match to avoid substrings inside longer tokens (e.g. 'fran' in 'frank')
        is_start_boundary = start_index == 0 or not norm_text[start_index - 1].isalnum()
        is_end_boundary = end_index == len(norm_text) - 1 or not norm_text[end_index + 1].isalnum()
        if not (is_start_boundary and is_end_boundary):
            continue
        raw_matches.append((start_index, end_index, canon, alias_length))

    if not raw_matches:
        return set()

    raw_matches.sort(key=lambda x: (x[0], -x[3]))

    accepted: List[Tuple[int, int, str, int]] = []
    for match in raw_matches:
        s, e, canon, length = match
        skip = False
        for as_, ae_, acanon, alen in accepted:
            if as_ <= s and e <= ae_ and (alen >= length) and acanon != canon:
                skip = True
                break
        if not skip:
            accepted.append(match)

    return {canon for _, _, canon, _ in accepted}

def filter_recent_articles(entries: List[Any], hours: int = 24) -> List[Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return [
        entry for entry in entries
        if hasattr(entry, 'published_parsed') and
           datetime.fromtimestamp(time.mktime(entry.published_parsed)).replace(tzinfo=timezone.utc) > cutoff
    ]

def get_canonical_entity(user_input: str, aliases: Dict[str, List[str]]) -> Optional[str]:
    norm_input = normalize_name(user_input)
    return aliases.get(norm_input, [None])[0]

# Export for WSGI deployment (Vercel, etc.)
application = app

# --- Main ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)