from flask import Flask, request, Response
import requests
from collections import Counter
from datetime import datetime, timedelta, timezone
import certifi
import re

app = Flask(__name__)

API_KEY = "df28d02564c64ca891c9e91da26e32fa"
ENDPOINT = "https://newsapi.org/v2/everything"

try:
    with open("player_names.txt", "r", encoding="utf-8") as f:
        KNOWN_PLAYERS = set(line.strip() for line in f if line.strip())
except FileNotFoundError:
    KNOWN_PLAYERS = set()
    print("⚠️  player_names.txt not found — no players loaded.")

@app.route("/", methods=["GET"])
def home():
    return Response("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Transfer Tracker</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400&display=swap" rel="stylesheet">
        <style>
            body {
                margin: 0;
                height: 100vh;
                background: linear-gradient(to bottom right, #eef6fb, #d7e9f7);
                font-family: 'Inter', sans-serif;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .container {
                text-align: center;
                background-color: rgba(255, 255, 255, 0.85);
                padding: 2rem 3rem;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            }
            h2 {
                margin-bottom: 1.2rem;
                color: #003366;
            }
            input[type="text"] {
                padding: 0.7rem;
                width: 250px;
                border: 1px solid #ccc;
                border-radius: 6px;
                font-size: 1rem;
                margin-bottom: 1rem;
            }
            button {
                padding: 0.7rem 1.5rem;
                font-size: 1rem;
                color: white;
                background-color: #0077cc;
                border: none;
                border-radius: 6px;
                cursor: pointer;
            }
            button:hover {
                background-color: #005fa3;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Football Transfer Tracker</h2>
            <form action="/transfers" method="get">
                <input type="text" id="team" name="team" placeholder="e.g. Arsenal" required>
                <br>
                <button type="submit">Search Transfers</button>
            </form>
        </div>
    </body>
    </html>
    """, mimetype="text/html")


@app.route("/transfers", methods=["GET"])
def get_transfer_mentions():
    team_name = request.args.get("team")
    if not team_name:
        return Response("Missing 'team' query parameter", status=400)

    query = f"{team_name} transfer"
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=3)

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
        return Response(f"<p>Failed to fetch news: {str(e)}</p>", mimetype="text/html")

    texts = [f"{a['title']} {a.get('description', '')}" for a in articles]
    combined_text = " ".join(texts).lower()

    frequency_counter = Counter()
    for player in KNOWN_PLAYERS:
        if player in EXCLUDED_NAMES:
            continue
        pattern = r"\b" + re.escape(player.lower()) + r"\b"
        matches = re.findall(pattern, combined_text, re.IGNORECASE)
        if matches:
            frequency_counter[player] = len(matches)

    html_head = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Transfer Results</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400&display=swap" rel="stylesheet">
        <style>
            body {{
                background: linear-gradient(to bottom right, #eef6fb, #d7e9f7);
                font-family: 'Inter', sans-serif;
                height: 100vh;
                margin: 0;
                display: flex;
                align-items: center;
                justify-content: center;
            }}
            .results-container {{
                background-color: rgba(255,255,255,0.85);
                padding: 2rem 3rem;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                text-align: left;
                max-width: 500px;
            }}
            h2 {{
                color: #003366;
                margin-bottom: 1rem;
                text-align: center;
            }}
            ul {{
                padding-left: 1.2rem;
            }}
            li {{
                margin-bottom: 0.8rem;
                line-height: 1.5;
            }}
            a {{
                color: #0077cc;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
        </style>
    </head>
    <body>
    <div class="results-container">
    <h2>Transfer Mentions: {team_name.title()}</h2>
    <ul>
    """

    html_body = ""
    if not frequency_counter:
        html_body += "<li>No players mentioned recently.</li>"
    else:
        for name, count in frequency_counter.most_common():
            search_name = name.replace(" ", "+")
            fbref_link = f"https://fbref.com/en/search/search.fcgi?search={search_name}"
            html_body += f'<li><strong>{name}</strong> ({name} has been mentioned {count} times): <a href="{fbref_link}" target="_blank">View stats</a></li>'

    html_footer = """
    </ul>
    </div>
    </body>
    </html>
    """

    return Response(html_head + html_body + html_footer, mimetype="text/html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
