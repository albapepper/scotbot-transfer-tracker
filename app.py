from flask import Flask, request, jsonify
import requests
import os

app = Flask(__name__)

OPTA_API_ENDPOINT = "https://api.opta-like.com/playerstats"  # Replace with your real endpoint
OPTA_API_KEY = os.environ.get("OPTA_API_KEY", "your_actual_key_here")  # Uses env variable if set

@app.route("/player")
def player_stats():
    player_name = request.args.get("name")
    if not player_name:
        return jsonify({"error": "Missing player name"}), 400

    params = {
        "name": player_name,
        "isPermittedDomain": "true",
        "apikey": OPTA_API_KEY
    }

    try:
        response = requests.get(OPTA_API_ENDPOINT, params=params)
        response.raise_for_status()
        stats = response.json()
    except Exception as e:
        return jsonify({"error": f"Failed to fetch data: {str(e)}"}), 500

    return jsonify({"player": player_name, "stats": stats})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
