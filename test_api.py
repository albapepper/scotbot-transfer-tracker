"""
Test script for the Data API
Run this to verify your API is working correctly
"""
from api_client import DataAPIClient
import os

def test_api():
    print("🧪 Testing Data API Connection...\n")
    
    # Initialize client
    api_url = os.getenv("DATA_API_URL", "http://localhost:8001")
    client = DataAPIClient(api_url)
    print(f"API URL: {api_url}")
    
    # Test 1: Health Check
    print("\n1️⃣ Testing Health Check...")
    health = client.health_check()
    if health:
        print(f"✅ API is healthy!")
        print(f"   Players loaded: {health.get('players_loaded', 0)}")
        print(f"   Player aliases: {health.get('player_aliases', 0)}")
        print(f"   Club aliases: {health.get('club_aliases', 0)}")
    else:
        print("❌ Health check failed - API may not be running")
        return
    
    # Test 2: Autocomplete
    print("\n2️⃣ Testing Autocomplete...")
    suggestions = client.autocomplete("messi")
    if suggestions:
        print(f"✅ Autocomplete working! Found {len(suggestions)} suggestions")
        print(f"   First few: {suggestions[:3]}")
    else:
        print("❌ Autocomplete failed or no results")
    
    # Test 3: Player Info
    print("\n3️⃣ Testing Player Info...")
    if suggestions:
        test_player = suggestions[0]
        player_info = client.get_player_info(test_player)
        if player_info:
            print(f"✅ Player info working!")
            print(f"   Player: {player_info.get('name')}")
            print(f"   Club: {player_info.get('club')}")
            print(f"   Position: {player_info.get('position')}")
        else:
            print("❌ Player info failed")
    
    # Test 4: Player Stats
    print("\n4️⃣ Testing Player Stats...")
    if suggestions:
        test_player = suggestions[0]
        player_stats = client.get_player_stats(test_player)
        if player_stats:
            print(f"✅ Player stats working!")
            stats = player_stats.get('stats', {})
            print(f"   Stats fields: {len(stats)} available")
            if stats:
                first_stat = list(stats.items())[0]
                print(f"   Sample stat: {first_stat[0]} = {first_stat[1]}")
        else:
            print("❌ Player stats failed")
    
    # Test 5: Team Autocomplete
    print("\n5️⃣ Testing Team Features...")
    team_suggestions = client.autocomplete("manchester")
    if team_suggestions:
        test_team = team_suggestions[0]
        print(f"✅ Found team: {test_team}")
        
        # Test team info
        team_info = client.get_team_info(test_team)
        if team_info:
            print(f"   Team info: {team_info.get('name')} ({team_info.get('league')})")
        
        # Test team roster
        roster = client.get_team_roster(test_team)
        if roster and roster.get('roster'):
            print(f"   Roster: {len(roster['roster'])} players")
    else:
        print("❌ Team features failed")
    
    print("\n🎉 API testing complete!")

if __name__ == "__main__":
    test_api()
