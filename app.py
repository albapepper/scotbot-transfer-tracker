
from flask import Flask, request, Response
import feedparser
from collections import Counter
from datetime import datetime, timedelta
import time
import re

app = Flask(__name__)

# Load known player names from file
try:
    with open("player_names.txt", "r", encoding="utf-8") as f:
        KNOWN_PLAYERS = set(line.strip() for line in f if line.strip())
    print(f"✅ Loaded {len(KNOWN_PLAYERS)} players from player_names.txt")
except FileNotFoundError:
    KNOWN_PLAYERS = set()
    print("⚠️ player_names.txt not found — no players loaded.")

# Filter articles published in the last 24 hours
def filter_recent_articles(entries, hours=24):
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    recent_entries = []
    for entry in entries:
        if hasattr(entry, 'published_parsed'):
            published = datetime.fromtimestamp(time.mktime(entry.published_parsed))
            if published > cutoff:
                recent_entries.append(entry)
    return recent_entries

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
                padding: 2rem 0;
                min-height: 100vh;
                background: linear-gradient(to bottom right, #eef6fb, #d7e9f7);
                font-family: 'Inter', sans-serif;
                display: flex;
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
                <input type="text" id="team" name="team" placeholder="e.g. Chelsea" required>
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

    query = f"{team_name} transfer".replace(" ", "+")
    rss_url = f"https://news.google.com/rss/search?q={query}"

    try:
        feed = feedparser.parse(rss_url)
        recent_articles = filter_recent_articles(feed.entries)
        texts = [entry.title + " " + entry.get("description", "") for entry in recent_articles]
    except Exception as e:
        return Response(f"<p>Failed to fetch news: {str(e)}</p>", mimetype="text/html")

    combined_text = " ".join(texts).lower()

    frequency_counter = Counter()
    for player in KNOWN_PLAYERS:
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
                margin: 0;
                padding: 2rem 0;
                min-height: 100vh;
                background: linear-gradient(to bottom right, #eef6fb, #d7e9f7);
                font-family: 'Inter', sans-serif;
                display: flex;
                justify-content: center;
            }}
            .results-container {{
                background-color: rgba(255,255,255,0.85);
                padding: 2rem 3rem;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                max-width: 500px;
                width: 100%;
            }}
            h2 {{
                color: #003366;
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
        html_body += "<li>No players mentioned in the last 24 hours.</li>"
    else:
        for name, count in frequency_counter.most_common():
            search_name = name.replace(" ", "+")
            fbref_link = f"https://fbref.com/en/search/search.fcgi?search={search_name}"
            html_body += f'<li><strong>{name}</strong> ({count} mentions): <a href="{fbref_link}" target="_blank">View stats</a></li>'

    html_footer = """
    </ul>
    </div>
    </body>
    </html>
    """

    return Response(html_head + html_body + html_footer, mimetype="text/html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
