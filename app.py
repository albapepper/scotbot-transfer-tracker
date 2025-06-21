
# soccer transfer API bot

import requests
from collections import Counter
from datetime import datetime, timedelta, timezone
import spacy
import certifi

# Load spaCy English model
nlp = spacy.load("en_core_web_sm")

# Your NewsAPI key here
API_KEY = "df28d02564c64ca891c9e91da26e32fa"
QUERY = "Chelsea transfer"
ENDPOINT = "https://newsapi.org/v2/everything"

# Time range: past 24 hours
now = datetime.now(timezone.utc)
yesterday = now - timedelta(days=1)

# Format dates for API
from_date = yesterday.isoformat()
to_date = now.isoformat()

# Request parameters
params = {
    "q": QUERY,
    "from": from_date,
    "to": to_date,
    "language": "en",
    "sortBy": "publishedAt",
    "apiKey": API_KEY,
    "pageSize": 100
}

# Fetch articles securely using certifi
response = requests.get(ENDPOINT, params=params, verify=certifi.where())
articles = response.json().get("articles", [])

# Combine titles and descriptions
texts = [f"{a['title']} {a.get('description', '')}" for a in articles]

# Extract player names using spaCy NER
player_names = []
for text in texts:
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            player_names.append(ent.text)

# Count mentions
mention_counts = Counter(player_names)

# Display results
print("Player mentions in the past 24 hours:")
for name, count in mention_counts.most_common():
    print(f"{name}: {count}")
