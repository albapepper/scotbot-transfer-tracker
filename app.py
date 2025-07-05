from flask import Flask, request, Response
import feedparser
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import time
import re
import urllib.parse

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
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return [
        entry for entry in entries
        if hasattr(entry, 'published_parsed') and
           datetime.fromtimestamp(time.mktime(entry.published_parsed)).replace(tzinfo=timezone.utc) > cutoff
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
    except Exception as e:
        return Response(f"<p>Failed to fetch news: {str(e)}</p>", mimetype="text/html")

    player_mentions = Counter()
    player_articles = defaultdict(set)

    for entry in recent_articles:
        text = (entry.title + " " + entry.get("description", "")).lower()
        for player in KNOWN_PLAYERS:
            pattern = rf"\b{re.escape(player.lower())}\b"
            if re.search(pattern, text):
                player_mentions[player] += 1
                player_articles[player].add((entry.title, entry.link, entry.get("description", "")))

    html = f"""
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
                text-align: center;
                background-color: white;
                padding: 2rem 3rem;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
                max-width: 600px;
            }}
            h2 {{
                color: #003366;
            }}
            ul {{
                list-style: none;
                padding-left: 0;
            }}
            li {{
                margin-bottom: 1rem;
                font-size: 1.1rem;
            }}
            a {{
                color: #0077cc;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            .back-button {{
                margin-top: 2rem;
            }}
            .btn {{
                display: inline-block;
                padding: 0.5rem 1rem;
                font-family: 'Times New Roman', serif;
                font-size: 1rem;
                color: white;
                background-color: #0077cc;
                border-radius: 6px;
                text-decoration: none;
            }}
            .btn:hover {{
                background-color: #005fa3;
            }}
        </style>
    </head>
    <body>
        <div class="results-container">
            <h2>Transfer Mentions: {team_name.title()}</h2>
            <ul>
    """

    if not player_mentions:
        html += "<li>No players mentioned in the last 24 hours.</li>"
    else:
        for player, count in player_mentions.most_common():
            encoded_name = urllib.parse.quote(player)
            html += f'<li><a href="/player?name={encoded_name}">{player}</a> — {count} mentions</li>'

    html += """
            </ul>
            <div class="back-button">
                <a href="/" class="btn">← Back to Search</a>
            </div>
        </div>
    </body>
    </html>
    """

    app.config["PLAYER_ARTICLES"] = player_articles
    return Response(html, mimetype="text/html")

@app.route("/player", methods=["GET"])
def player_detail():
    player_name = request.args.get("name")
    if not player_name:
        return Response("Missing 'name' query parameter", status=400)

    decoded_name = urllib.parse.unquote(player_name)
    fbref_link = f"https://fbref.com/en/search/search.fcgi?search={decoded_name.replace(' ', '+')}"
    articles = app.config.get("PLAYER_ARTICLES", {}).get(decoded_name, set())

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{decoded_name} Mentions</title>
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
                text-align: center;
                background-color: white;
                padding: 2rem 3rem;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
                max-width: 700px;
            }}
            h2 {{
                color: #003366;
            }}
            ul {{
                list-style: none;
                padding-left: 0;
                text-align: left;
            }}
            li {{
                margin-bottom: 1.5rem;
            }}
            a {{
                color: #0077cc;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            .back-button {{
                margin-top: 2rem;
                text-align: center;
            }}
            .btn {{
                display: inline-block;
                padding: 0.5rem 1rem;
                font-family: 'Times New Roman', serif;
                font-size: 1rem;
                color: white;
                background-color: #0077cc;
                border-radius: 6px;
                text-decoration: none;
            }}
            .btn:hover {{
                background-color: #005fa3;
            }}
        </style>
    </head>
    <body>
        <div class="results-container">
            <h2>{decoded_name}: <a href="{fbref_link}" target="_blank">stats</a></h2>
            <ul>
    """
    if not articles:
        html += "<li>No articles found for this player.</li>"
    else:
        for title, link, desc in sorted(articles):
            html += f"""
            <li>
                <a href="{link}" target="_blank"><strong>{title}</strong></a><br>
                {desc}
            </li>
            """

    html += """
            </ul>
            <div class="back-button">
                <a href="/" class="btn">← Back to Search</a>
            </div>
        </div>
    </body>
    </html>
    """
    return Response(html, mimetype="text/html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
