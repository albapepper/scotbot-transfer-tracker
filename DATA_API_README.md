# Scotbot Data API

A FastAPI-based data service for serving football/soccer statistics.

## Repository Structure

```
scotbot-data-api/
├── app.py                      # FastAPI application
├── data/                       # SQL data files
│   ├── player-stats.sql
│   ├── team-stats.sql
│   └── future-leagues/         # For expansion
├── scripts/                    # Data generation scripts
│   ├── generate-player-stats.py
│   ├── generate-team-stats.py
│   └── generate_player_names.py
├── requirements.txt
├── README.md
└── vercel.json                 # For Vercel deployment
```

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Place your SQL data files in the `data/` directory

3. Run the development server:
```bash
python app.py
```

Or with uvicorn:
```bash
uvicorn app:app --host 0.0.0.0 --port 8001 --reload
```

## API Endpoints

- `GET /` - API information and available endpoints
- `GET /autocomplete?query=string` - Get autocomplete suggestions
- `GET /player/{player_name}` - Get basic player information
- `GET /player/{player_name}/stats` - Get detailed player statistics
- `GET /team/{team_name}` - Get basic team information
- `GET /team/{team_name}/stats` - Get detailed team statistics and roster
- `GET /team/{team_name}/roster` - Get team roster only
- `GET /aliases` - Get all aliases for entity recognition
- `GET /health` - Health check

## Data Generation

Use the scripts in the `scripts/` directory to generate updated data:

```bash
cd scripts/
python generate-player-stats.py
python generate-team-stats.py
```

## Deployment

### Vercel
The repository includes a `vercel.json` configuration for easy deployment to Vercel.

### Other Platforms
The FastAPI app can be deployed to any platform that supports Python web applications:
- Railway
- Render
- Heroku
- AWS Lambda (with Mangum)

## Environment Variables

- `DATA_API_URL`: Base URL for the API (for client applications)

## Adding New Leagues

1. Add the new league data to appropriate SQL files in `data/`
2. Update the generation scripts in `scripts/` if needed
3. The API will automatically serve the new data

## Client Usage

The main application uses the `api_client.py` to communicate with this service:

```python
from api_client import api_client

# Get player info
player = api_client.get_player_info("Messi")

# Get autocomplete suggestions
suggestions = api_client.autocomplete("Manc")

# Get team roster
roster = api_client.get_team_roster("Manchester United")
```
