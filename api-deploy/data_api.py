# --- Data API Server ---
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Optional, Tuple, Any
import unicodedata
import re
import os
from pathlib import Path
from dataclasses import dataclass
import ahocorasick
from pydantic import BaseModel

# --- FastAPI App Setup ---
app = FastAPI(title="Scotbot Football Data API", version="1.0.0")

# Add CORS middleware to allow requests from your main app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your main app's domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Data Models ---
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

class PlayerStatsResponse(BaseModel):
    player_info: Optional[Dict[str, str]]
    stats: Optional[Dict[str, str]]

class TeamStatsResponse(BaseModel):
    team_info: Optional[Dict[str, str]]
    stats: Optional[Dict[str, str]]
    roster: List[Dict[str, Any]]

class AutocompleteResponse(BaseModel):
    suggestions: List[str]

class AliasesResponse(BaseModel):
    player_aliases: Dict[str, List[str]]
    club_aliases: Dict[str, List[str]]

# --- Helper Functions ---
def normalize_name(s: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFD', s.lower())
        if unicodedata.category(c) != 'Mn'
    )

def normalize_team_name(s: str) -> str:
    """Enhanced normalization for team names including common abbreviations"""
    return ''.join(
        c for c in unicodedata.normalize('NFD', s.lower()) 
        if unicodedata.category(c) != 'Mn'
    ).replace(' fc','').replace(' afc','').replace('.','').replace(',','').replace('-',' ').strip()

def parse_sql_columns(file_path: str, table_name: str) -> List[str]:
    """Extract column names from SQL CREATE TABLE statement"""
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
            create_match = re.search(rf"CREATE TABLE.*?{table_name}\s*\((.*?)\);", content, re.DOTALL | re.IGNORECASE)
            if create_match:
                columns_text = create_match.group(1)
                return re.findall(r"`([^`]+)`", columns_text)
    except FileNotFoundError:
        return []
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
    
    try:
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
    except FileNotFoundError:
        return None
    return None

def load_player_data(filename: str) -> Tuple[Dict[str, List[str]], Dict[str, List[str]], Dict[str, PlayerInfo]]:
    player_aliases: Dict[str, List[str]] = {}
    club_aliases: Dict[str, List[str]] = {}
    player_lookup: Dict[str, PlayerInfo] = {}
    
    if not os.path.exists(filename):
        return player_aliases, club_aliases, player_lookup
        
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

def add_aliases(aliases_dict: Dict[str, List[str]], replacements: List[Tuple[str, str]]) -> Dict[str, List[str]]:
    new_aliases: Dict[str, List[str]] = {}
    for norm_alias, canon_list in list(aliases_dict.items()):
        for old, new in replacements:
            if old in norm_alias:
                alt_alias = norm_alias.replace(old, new)
                if alt_alias not in aliases_dict:
                    new_aliases[alt_alias] = canon_list
    aliases_dict.update(new_aliases)
    return aliases_dict

def get_canonical_entity(user_input: str, aliases: Dict[str, List[str]]) -> Optional[str]:
    norm_input = normalize_name(user_input)
    return aliases.get(norm_input, [None])[0]

# --- Data Loading ---
DATA_DIR = Path(__file__).parent / "data"
PLAYER_FILE = DATA_DIR / "player-stats.sql"

# Initialize global variables (will be loaded on first request)
player_aliases = {}
club_aliases = {}
PLAYER_LOOKUP = {}
_data_loaded = False

def ensure_data_loaded():
    """Lazy load data on first request (better for serverless)"""
    global player_aliases, club_aliases, PLAYER_LOOKUP, _data_loaded
    if not _data_loaded:
        try:
            player_aliases, club_aliases, PLAYER_LOOKUP = load_player_data(str(PLAYER_FILE))
            # Add club aliases
            club_aliases = add_aliases(club_aliases, [
                ("utd", "united"), ("united", "utd"),
                ("manchester united", "man united"), ("man united", "manchester united"),
                ("manchester city", "man city"), ("man city", "manchester city"),
                ("man united", "man u"), ("man u", "man united"),
                ("nott'ham forest", "nottingham forest"), ("nottingham forest", "nott'ham forest")
            ])
            _data_loaded = True
        except Exception as e:
            print(f"Error loading data: {e}")
            # Set empty defaults to prevent crashes
            player_aliases = {}
            club_aliases = {}
            PLAYER_LOOKUP = {}
            _data_loaded = True

# Add club aliases
club_aliases = add_aliases(club_aliases, [
    ("utd", "united"), ("united", "utd"),
    ("manchester united", "man united"), ("man united", "manchester united"),
    ("manchester city", "man city"), ("man city", "manchester city"),
    ("man united", "man u"), ("man u", "man united"),
    ("nott'ham forest", "nottingham forest"), ("nottingham forest", "nott'ham forest")
])

# --- API Endpoints ---
@app.get("/", response_model=Dict[str, str])
def root():
    return {
        "message": "Scotbot Football Data API", 
        "version": "1.0.0",
        "endpoints": {
            "autocomplete": "/autocomplete?query=string",
            "player": "/player/{player_name}",
            "player_stats": "/player/{player_name}/stats", 
            "team": "/team/{team_name}",
            "team_stats": "/team/{team_name}/stats",
            "team_roster": "/team/{team_name}/roster",
            "aliases": "/aliases"
        }
    }

@app.get("/autocomplete", response_model=AutocompleteResponse)
def autocomplete(query: str = Query(..., description="Search query for autocomplete")):
    """Get autocomplete suggestions for players and teams"""
    ensure_data_loaded()
    query = query.strip().lower()
    suggestions = set()
    
    if query:
        # Search player aliases
        for norm_name, names in player_aliases.items():
            for name in names:
                if query in name.lower():
                    suggestions.add(name)
        
        # Search club aliases
        for norm_name, names in club_aliases.items():
            for name in names:
                if query in name.lower():
                    suggestions.add(name)
    
    return AutocompleteResponse(suggestions=sorted(suggestions)[:10])

@app.get("/player/{player_name}")
def get_player_info(player_name: str):
    """Get basic player information"""
    ensure_data_loaded()
    canonical_player = get_canonical_entity(player_name, player_aliases)
    if not canonical_player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    player_info = PLAYER_LOOKUP.get(canonical_player.lower())
    if not player_info:
        raise HTTPException(status_code=404, detail="Player info not found")
    
    return {
        "name": player_info.name,
        "born": player_info.born,
        "position": player_info.position,
        "club": player_info.club,
        "nationality": player_info.nationality
    }

@app.get("/player/{player_name}/stats", response_model=PlayerStatsResponse)
def get_player_stats(player_name: str):
    """Get detailed player statistics"""
    ensure_data_loaded()
    canonical_player = get_canonical_entity(player_name, player_aliases)
    if not canonical_player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Get basic player info
    player_info = PLAYER_LOOKUP.get(canonical_player.lower())
    player_info_dict = None
    if player_info:
        player_info_dict = {
            "name": player_info.name,
            "born": player_info.born,
            "position": player_info.position,
            "club": player_info.club,
            "nationality": player_info.nationality
        }
    
    # Get detailed stats
    player_file = str(PLAYER_FILE)
    stat_keys = parse_sql_columns(player_file, "player_stats")
    stats_row = find_sql_row_by_name(player_file, "player_stats", 1, canonical_player)
    
    player_stats = {}
    if stats_row and stat_keys and len(stats_row) == len(stat_keys):
        excluded_keys = {'Rk', 'Player', 'Nation', 'Pos', 'Squad', 'Born', 'Matches'}
        for key, value in zip(stat_keys, stats_row):
            if key not in excluded_keys:
                player_stats[key] = value
    
    return PlayerStatsResponse(
        player_info=player_info_dict,
        stats=player_stats if player_stats else None
    )

@app.get("/team/{team_name}")
def get_team_info(team_name: str):
    """Get basic team information"""
    team_file = DATA_DIR / "team-stats.sql"
    stats_row = find_sql_row_by_name(str(team_file), "team_stats", 2, team_name, normalize_team_name)
    
    if not stats_row or len(stats_row) < 3:
        raise HTTPException(status_code=404, detail="Team not found")
    
    league = stats_row[0] if stats_row else "Unknown"
    country = stats_row[1] if len(stats_row) > 1 else "Unknown"
    name = stats_row[2]
    
    return {
        "name": name,
        "league": league,
        "country": country
    }

@app.get("/team/{team_name}/stats", response_model=TeamStatsResponse)
def get_team_stats(team_name: str):
    """Get detailed team statistics and roster"""
    ensure_data_loaded()
    # Get team info
    team_file = DATA_DIR / "team-stats.sql"
    stats_row = find_sql_row_by_name(str(team_file), "team_stats", 2, team_name, normalize_team_name)
    
    team_info_dict = None
    team_stats = {}
    
    if stats_row and len(stats_row) >= 3:
        league = stats_row[0] if stats_row else "Unknown"
        country = stats_row[1] if len(stats_row) > 1 else "Unknown"
        name = stats_row[2]
        team_info_dict = {
            "name": name,
            "league": league,
            "country": country
        }
        
        # Get team stats
        stat_keys = parse_sql_columns(str(team_file), "team_stats")
        if stat_keys and len(stats_row) == len(stat_keys):
            for key, value in zip(stat_keys, stats_row):
                team_stats[key] = value
    
    # Get roster
    roster = []
    for player_info in PLAYER_LOOKUP.values():
        if player_info.club.lower() == team_name.lower():
            roster.append({
                'name': player_info.name,
                'born': player_info.born,
                'position': player_info.position,
                'nationality': player_info.nationality
            })
    
    return TeamStatsResponse(
        team_info=team_info_dict,
        stats=team_stats if team_stats else None,
        roster=roster
    )

@app.get("/team/{team_name}/roster")
def get_team_roster(team_name: str):
    """Get team roster only"""
    ensure_data_loaded()
    roster = []
    for player_info in PLAYER_LOOKUP.values():
        if player_info.club.lower() == team_name.lower():
            roster.append({
                'name': player_info.name,
                'born': player_info.born,
                'position': player_info.position,
                'nationality': player_info.nationality
            })
    
    if not roster:
        raise HTTPException(status_code=404, detail="Team not found or no players in roster")
    
    return {"team": team_name, "roster": roster}

@app.get("/aliases", response_model=AliasesResponse)
def get_aliases():
    """Get all player and club aliases for entity recognition"""
    ensure_data_loaded()
    return AliasesResponse(
        player_aliases=player_aliases,
        club_aliases=club_aliases
    )

# --- Health Check ---
@app.get("/health")
def health_check():
    try:
        ensure_data_loaded()
        return {
            "status": "healthy",
            "players_loaded": len(PLAYER_LOOKUP),
            "player_aliases": len(player_aliases),
            "club_aliases": len(club_aliases)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "players_loaded": 0,
            "player_aliases": 0,
            "club_aliases": 0
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
