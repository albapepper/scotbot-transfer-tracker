"""
Hybrid API Client with Local Fallback
Tries cloud API first, falls back to local data processing
"""
import requests
from typing import Dict, List, Optional, Any
import urllib.parse
import os
from api_client import DataAPIClient

class HybridDataClient:
    def __init__(self):
        # Try cloud API first, then local API
        self.cloud_client = DataAPIClient("https://scotbot-data-8enodx7wm-albapeppers-projects.vercel.app")
        self.local_client = DataAPIClient("http://localhost:8001")
        self.fallback_data = None
        
    def _get_working_client(self):
        """Determine which client is working"""
        # Try cloud first
        if self.cloud_client.health_check():
            return self.cloud_client
        
        # Try local second
        if self.local_client.health_check():
            return self.local_client
            
        # No API available
        return None
    
    def _load_fallback_data(self):
        """Load fallback data from local files if APIs are down"""
        if self.fallback_data is not None:
            return
        
        try:
            # Import local data processing functions
            from data_api import load_player_data, add_aliases, normalize_name
            
            # Load data
            player_file = "data/player-stats.sql"
            if os.path.exists(player_file):
                player_aliases, club_aliases, player_lookup = load_player_data(player_file)
                club_aliases = add_aliases(club_aliases, [
                    ("utd", "united"), ("united", "utd"),
                    ("manchester united", "man united"), ("man united", "manchester united"),
                    ("manchester city", "man city"), ("man city", "manchester city"),
                    ("man united", "man u"), ("man u", "man united"),
                    ("nott'ham forest", "nottingham forest"), ("nottingham forest", "nott'ham forest")
                ])
                
                self.fallback_data = {
                    "player_aliases": player_aliases,
                    "club_aliases": club_aliases,
                    "player_lookup": player_lookup
                }
            else:
                self.fallback_data = {
                    "player_aliases": {},
                    "club_aliases": {},
                    "player_lookup": {}
                }
        except Exception as e:
            print(f"Could not load fallback data: {e}")
            self.fallback_data = {
                "player_aliases": {},
                "club_aliases": {},
                "player_lookup": {}
            }
    
    def autocomplete(self, query: str) -> List[str]:
        """Get autocomplete suggestions with fallback"""
        client = self._get_working_client()
        if client:
            result = client.autocomplete(query)
            if result:
                return result
        
        # Fallback to local processing
        self._load_fallback_data()
        suggestions = set()
        query_lower = query.lower()
        
        # Search player aliases
        for names in self.fallback_data["player_aliases"].values():
            for name in names:
                if query_lower in name.lower():
                    suggestions.add(name)
        
        # Search club aliases  
        for names in self.fallback_data["club_aliases"].values():
            for name in names:
                if query_lower in name.lower():
                    suggestions.add(name)
        
        return sorted(suggestions)[:10]
    
    def get_player_info(self, player_name: str) -> Optional[Dict[str, str]]:
        """Get player info with fallback"""
        client = self._get_working_client()
        if client:
            result = client.get_player_info(player_name)
            if result:
                return result
        
        # Fallback - basic implementation
        return {"name": player_name, "status": "API unavailable"}
    
    def get_aliases(self) -> Optional[Dict[str, Dict[str, List[str]]]]:
        """Get aliases with fallback"""
        client = self._get_working_client()
        if client:
            result = client.get_aliases()
            if result:
                return result
        
        # Fallback
        self._load_fallback_data()
        return {
            "player_aliases": self.fallback_data["player_aliases"],
            "club_aliases": self.fallback_data["club_aliases"]
        }

# Global hybrid client
hybrid_client = HybridDataClient()
