from flask import Flask, request, Response
import feedparser
from collections import Counter
from datetime import datetime, timedelta
import time
from rapidfuzz import fuzz
import re

app = Flask(__name__)

# Load known player names from file
try:
    with open("player_names.txt", "r", encoding="utf-8") as f:
        KNOWN_PLAYERS = [line.strip() for line in f if line.strip()]
    print(f"✅ Loaded {len(KNOWN_PLAYERS)} players from player_names.txt")
except FileNotFoundError:
    KNOWN_PLAYERS = []
    print("⚠️ player_names.txt not found — no players loaded.")

def filter_recent_articles(entries, hours=24):
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    return [
        entry for entry in entries
        if hasattr(entry, 'published_parsed') and
           datetime.fromtimestamp(time.mktime(entry.published_parsed)) > cutoff
    ]

@app.route("/", methods=["GET"])
def home():
    return Response("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Transfer Tracker</title>
        <style>
            html, body {
                margin: 0;
                padding: 0;
                height: 100%;
                background-color: white;
                font-family: 'Times New Roman', serif;
                display: flex;
                justify-content: center;
                align-items: center;
            }
            .container {
                text-align: center;
                background-color: white;
                padding: 2rem 3rem;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            }
            h1 {
                font-size: 2rem;
                margin-bottom: 1.5rem;
                color: #003366;
            }
            input[type="text"] {
                padding: 0.6rem;
                width: 240px;
                border: 1px solid #ccc;
                border-radius: 6px;
                font-size: 1rem;
                font-family: 'Times New Roman', serif;
            }
            button {
                margin-top: 1rem;
                padding: 0.6rem 1.2rem;
                font-size: 1rem;
                font-family: 'Times New Roman', serif;
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
            <h1>Transfer Tracker</h1>
            <form action="/transfers" method="get">
                <input type="text" name="team" placeholder="e.g. Chelsea" required>
                <br>
                <button type="submit">Search</button>
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

    rss_url = f"https://news.google.com/rss/search?q={team_name.replace(' ', '+')}+transfer"
    try:
        feed = feedparser.parse(rss_url)
        recent_articles = filter_recent_articles(feed.entries)
        combined_text = " ".join(
            (entry.title + " " + entry.get("description", "")).lower()
            for entry in recent_articles
        )
    except Exception as e:
        return Response(f"<p>Failed to fetch news: {str(e)}</p>", mimetype="text/html")

    frequency_counter = Counter()
    for player in KNOWN_PLAYERS:
        matches = re.findall(rf"\b{re.escape(player.lower())}\b", combined_text)
        if matches:
            frequency_counter[player] = len(matches)

    html_head = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Transfer Results</title>
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                height: 100%;
                background-color: white;
                font-family: 'Times New Roman', serif;
                display: flex;
                justify-content: center;
                align-items: center;
            }}
            .results-container {{
                background-color: white;
                padding: 2rem 3rem;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
                max-width: 600px;
                width: 100%;
                text-align: center;
            }}
            h2 {{
                color: #003366;
                text-align: center;
            }}
            ul {{
                padding-left: 0;
                list-style: none;
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
            html_body += f'<li><strong>{name}</strong> — mentioned {count} times within the past 24 hours: <a href="{fbref_link}" target="_blank">View stats</a></li>'

    html_footer = """
    </ul>
    </div>
    </body>
    </html>
    """

    return Response(html_head + html_body + html_footer, mimetype="text/html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
