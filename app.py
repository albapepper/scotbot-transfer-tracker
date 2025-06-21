from flask import Flask, request, jsonify
import requests
from collections import Counter
from datetime import datetime, timedelta, timezone
import spacy
import certifi

app = Flask(__name__)
nlp = spacy.load("en_core_web_sm")

API_KEY = "df28d02564c64ca891c9e91da26e32fa"
ENDPOINT = "https://newsapi.org/v2/everything"

@app.route("/transfers", methods=["GET"])
def get_transfer_mentions():
    team_name = request.args.get("team")
    if not team_name:
        return jsonify({"error": "Missing 'team' query parameter"}), 400

    query = f"{team_name} transfer"
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    params = {
        "q": query,
        "from": yesterday.isoformat(),
        "to": now.isoformat(),
        "language": "en",
        "sortBy": "publishedAt",
        "apiKey": API_KEY,
        "pageSize": 100
    }

    try:
        response = requests.get(ENDPOINT, params=params, verify=certifi.where())
        response.raise_for_status()
        articles = response.json().get("articles", [])
    except Exception as e:
        return jsonify({"error": f"Failed to fetch news: {str(e)}"}), 500

    texts = [f"{a['title']} {a.get('description', '')}" for a in articles]
    player_names = []

    for text in texts:
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                player_names.append(ent.text)

    mention_counts = Counter(player_names)
    results = []

    for name, count in mention_counts.most_common():
        search_name = name.replace(" ", "+")
        fbref_link = f"https://fbref.com/en/search/search.fcgi?search={search_name}"
        results.append({
            "player": name,
            "mentions": count,
            "fbref_link": fbref_link
        })

    return jsonify({
        "team": team_name,
        "results": results
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
