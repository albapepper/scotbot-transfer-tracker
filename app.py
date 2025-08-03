
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

# --- Flask App Setup ---
app = Flask(__name__)

# --- Routes ---
@app.route("/", methods=["GET"])
def home():
    return render_template("home.html")

@app.route("/autocomplete", methods=["GET"])
def autocomplete():
    query = request.args.get("query", "").strip().lower()
    suggestions = set()
    if query:
        for norm_name, names in player_aliases.items():
            for name in names:
                if query in name.lower():
                    suggestions.add(name)
        for norm_name, names in club_aliases.items():
            for name in names:
                if query in name.lower():
                    suggestions.add(name)
    return jsonify(sorted(suggestions)[:10])

@app.route("/transfers", methods=["GET"])
def get_transfer_mentions():
    query = request.args.get("query", "").rstrip()
    search_type = request.args.get("type", "team")
    window = 48  # Standardized 48 hour window

    if not query:
        return render_error("Missing 'query' parameter")

    try:
        recent_articles = fetch_recent_articles(query, hours=window)
    except Exception as e:
        return render_template("home.html", error=f"Failed to fetch news: {str(e)}")

    canonical_team = get_canonical_entity(query, club_aliases)
    canonical_player = get_canonical_entity(query, player_aliases)

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
    else:
        # Neither player nor team found, default to player template with no results
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
    canonical_player = get_canonical_entity(decoded_player, player_aliases)
    canonical_team = get_canonical_entity(decoded_team, club_aliases)
    if not canonical_player or not canonical_team:
        return render_error("Player or team not found")
    try:
        search_query = f"{decoded_player} {decoded_team}"
        recent_articles = fetch_recent_articles(search_query, hours=window)
    except Exception as e:
        return render_error(f"Failed to fetch news: {str(e)}")
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
    team_players = get_players_for_team(decoded_team)
    # --- TeamInfo ---
    team_info = get_team_info(decoded_team)
    # --- Team Stats ---
    team_file = DATA_DIR / "team-stats.sql"
    stat_keys = parse_sql_columns(str(team_file), "team_stats")
    stats_row = find_sql_row_by_name(str(team_file), "team_stats", 2, decoded_team, normalize_team_name)
    
    team_stats = {}
    if stats_row and stat_keys and len(stats_row) == len(stat_keys):
        for key, value in zip(stat_keys, stats_row):
            team_stats[key] = value
    
    context = build_team_roster_context(decoded_team, team_players)
    context["team_info"] = team_info
    context["team_stats"] = team_stats if team_stats else None
    return render_template("team-stats.html", **context)

@app.route("/player-stats", methods=["GET"])
def player_stats_page():
    player_name = request.args.get("player", "").strip()
    if not player_name:
        return render_error("Missing player parameter")
    decoded_player = urllib.parse.unquote(player_name)
    canonical_player = get_canonical_entity(decoded_player, player_aliases)
    if not canonical_player:
        return render_error("Player not found")
    
    player_file = str(PLAYER_FILE)
    stat_keys = parse_sql_columns(player_file, "player_stats")
    stats_row = find_sql_row_by_name(player_file, "player_stats", 1, canonical_player)
    
    player_stats = {}
    if stats_row and stat_keys and len(stats_row) == len(stat_keys):
        excluded_keys = {'Rk', 'Player', 'Nation', 'Pos', 'Squad', 'Born', 'Matches'}
        for key, value in zip(stat_keys, stats_row):
            if key not in excluded_keys:
                player_stats[key] = value
    
    player_info = get_player_info(canonical_player)
    linked_teams = []
    context = build_player_context(canonical_player, player_info, linked_teams, show_stats_link=False)
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

# --- SQL Parsing Helper Functions ---
def normalize_team_name(s: str) -> str:
    """Enhanced normalization for team names including common abbreviations"""
    return ''.join(
        c for c in unicodedata.normalize('NFD', s.lower()) 
        if unicodedata.category(c) != 'Mn'
    ).replace(' fc','').replace(' afc','').replace('.','').replace(',','').replace('-',' ').strip()

def parse_sql_columns(file_path: str, table_name: str) -> List[str]:
    """Extract column names from SQL CREATE TABLE statement"""
    with open(file_path, encoding="utf-8") as f:
        content = f.read()
        create_match = re.search(rf"CREATE TABLE.*?{table_name}\s*\((.*?)\);", content, re.DOTALL | re.IGNORECASE)
        if create_match:
            columns_text = create_match.group(1)
            return re.findall(r"`([^`]+)`", columns_text)
    return []

def split_sql_values(raw_string: str) -> List[str]:
    """Split CSV values while respecting quoted strings"""
    return [v.strip().strip("'") for v in re.split(r",(?=(?:[^']*'[^']*')*[^']*$)", raw_string)]

def find_sql_row_by_name(file_path: str, table_name: str, name_column_index: int, target_name: str, 
                        normalize_func=None) -> Optional[List[str]]:
    """Find a row in SQL file by matching a name in a specific column"""
    if normalize_func is None:
        normalize_func = normalize_name
    
    insert_pattern = rf"INSERT INTO {table_name} VALUES \((.*?)\);"
    insert_re = re.compile(insert_pattern, re.IGNORECASE)
    norm_target = normalize_func(target_name)
    
    with open(file_path, encoding="utf-8") as f:
        for line in f:
            match = insert_re.match(line.strip())
            if not match:
                continue
            raw = match.group(1)
            values = split_sql_values(raw)
            if len(values) > name_column_index:
                norm_sql_name = normalize_func(values[name_column_index])
                # Allow exact or partial match
                if (norm_target == norm_sql_name or 
                    norm_target in norm_sql_name or 
                    norm_sql_name in norm_target):
                    return values
    return None

def get_player_info(canonical_player: str) -> 'PlayerInfo|None':
    if not canonical_player:
        return None
    return PLAYER_LOOKUP.get(canonical_player.lower())

def get_players_for_team(team_name: str) -> list[dict]:
    players = []
    for player_info in PLAYER_LOOKUP.values():
        if player_info.club.lower() == team_name.lower():
            age = calculate_age_from_birth_year(player_info.born)
            nationality_full = convert_nationality_to_full_name(player_info.nationality)
            players.append({
                'name': player_info.name,
                'born': player_info.born,
                'age': age,
                'position': player_info.position,
                'nationality': nationality_full,
                'link': f"/transfers?query={urllib.parse.quote(player_info.name)}&type=player"
            })
    return players

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
    # Load from team-stats.sql (simple parse, not efficient for large files)
    team_file = DATA_DIR / "team-stats.sql"
    stats_row = find_sql_row_by_name(str(team_file), "team_stats", 2, canonical_team, normalize_team_name)
    
    if stats_row and len(stats_row) >= 3:
        league = stats_row[0] if stats_row else "Unknown"
        country = stats_row[1] if len(stats_row) > 1 else "Unknown"
        name = stats_row[2]
        current_roster = f"/team-stats?name={urllib.parse.quote(name)}"
        return TeamInfo(name=name, league=league, country=country, current_roster=current_roster)
    return None

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
            raw = match.group(1)
            values = split_sql_values(raw)
            if len(values) < 6:
                continue
            name = values[1]
            nationality = values[2] if len(values) > 2 and values[2] else "Unknown"
            position = values[3] if values[3] else "Unknown"
            club = values[4] if values[4] else "Unknown"
            born = values[6] if len(values) > 6 and values[6] else "Unknown"
            norm_name = normalize_name(name)
            player_aliases.setdefault(norm_name, []).append(name)
            player_lookup[name.lower()] = PlayerInfo(name, born, position, club, nationality)
            if club != "Unknown":
                norm_club = normalize_name(club)
                club_aliases.setdefault(norm_club, []).append(club)
    return player_aliases, club_aliases, player_lookup

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
    found: Set[str] = set()
    for end_index, (canon, alias_length) in automaton.iter(norm_text):
        start_index = end_index - alias_length + 1
        
        # For very short matches (2-3 chars), require word boundaries to avoid false positives
        if alias_length <= 3:
            # Check if the match is surrounded by word boundaries (non-alphanumeric chars)
            is_start_boundary = start_index == 0 or not norm_text[start_index - 1].isalnum()
            is_end_boundary = end_index == len(norm_text) - 1 or not norm_text[end_index + 1].isalnum()
            
            if is_start_boundary and is_end_boundary:
                found.add(canon)
        else:
            # For longer matches, add them as before
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
    norm_input = normalize_name(user_input)
    return aliases.get(norm_input, [None])[0]

# --- Data Loading ---
DATA_DIR = Path(__file__).parent
PLAYER_FILE = DATA_DIR / "player-stats.sql"
player_aliases, club_aliases, PLAYER_LOOKUP = load_player_data(str(PLAYER_FILE))
club_aliases = add_aliases(club_aliases, [
    ("utd", "united"), ("united", "utd"),
    ("manchester united", "man united"), ("man united", "manchester united"),
    ("manchester city", "man city"), ("man city", "manchester city"),
    ("man united", "man u"), ("man u", "man united"),
    ("nott'ham forest", "nottingham forest"), ("nottingham forest", "nott'ham forest")
])
player_automaton = build_automaton(player_aliases)
club_automaton = build_automaton(club_aliases)

# Export for WSGI deployment (Vercel, etc.)
application = app

# --- Main ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)