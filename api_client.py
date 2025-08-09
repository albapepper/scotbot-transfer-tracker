"""
API Client for Scotbot Data API
Handles communication with the data API service
"""
import requests
from typing import Dict, List, Optional, Any
import urllib.parse
import os

class DataAPIClient:
    def __init__(self, base_url: str = None):
        """
        Initialize the API client
        Args:
            base_url: Base URL for the data API. If None, will use environment variable or default
        """
        self.base_url = base_url or os.getenv("DATA_API_URL", "http://localhost:8001")
        if self.base_url.endswith("/"):
            self.base_url = self.base_url[:-1]
    
    def _make_request(self, endpoint: str, params: Dict = None) -> Any:
        """Make a request to the API and handle errors"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            return None
    
    def autocomplete(self, query: str) -> List[str]:
        """Get autocomplete suggestions"""
        data = self._make_request("/autocomplete", {"query": query})
        return data.get("suggestions", []) if data else []
    
    def get_player_info(self, player_name: str) -> Optional[Dict[str, str]]:
        """Get basic player information"""
        encoded_name = urllib.parse.quote(player_name)
        return self._make_request(f"/player/{encoded_name}")
    
    def get_player_stats(self, player_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed player statistics"""
        encoded_name = urllib.parse.quote(player_name)
        return self._make_request(f"/player/{encoded_name}/stats")
    
    def get_team_info(self, team_name: str) -> Optional[Dict[str, str]]:
        """Get basic team information"""
        encoded_name = urllib.parse.quote(team_name)
        return self._make_request(f"/team/{encoded_name}")
    
    def get_team_stats(self, team_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed team statistics and roster"""
        encoded_name = urllib.parse.quote(team_name)
        return self._make_request(f"/team/{encoded_name}/stats")
    
    def get_team_roster(self, team_name: str) -> Optional[Dict[str, Any]]:
        """Get team roster only"""
        encoded_name = urllib.parse.quote(team_name)
        return self._make_request(f"/team/{encoded_name}/roster")
    
    def get_aliases(self) -> Optional[Dict[str, Dict[str, List[str]]]]:
        """Get all player and club aliases for entity recognition"""
        return self._make_request("/aliases")
    
    def health_check(self) -> Optional[Dict[str, Any]]:
        """Check API health and status"""
        return self._make_request("/health")

# Global instance
api_client = DataAPIClient()
