# Migration Guide: Separating Data API from Main App

This guide walks you through migrating from a monolithic app to a separate data API architecture.

## Overview

**Before:** Single repository with app logic + data files
**After:** Two repositories - main app consuming data API

## Step 1: Create New Data Repository

1. Create a new GitHub repository: `scotbot-data-api`

2. Set up the repository structure:
```
scotbot-data-api/
├── app.py                      # Copy from: data_api.py
├── data/                       # Create new directory
│   ├── player-stats.sql        # Move from main repo
│   ├── team-stats.sql          # Move from main repo
│   └── future-leagues/         # For expansion
├── scripts/                    # Create new directory
│   ├── generate-player-stats.py    # Move from main repo
│   ├── generate-team-stats.py      # Move from main repo
│   └── generate_player_names.py    # Move from main repo
├── requirements.txt            # Copy from: data_api_requirements.txt
├── vercel.json                 # Copy from: data_api_vercel.json
└── README.md                   # Copy from: DATA_API_README.md
```

## Step 2: Move Files to Data Repository

### Files to Move from Current Repository:
- `player-stats.sql` → `data/player-stats.sql`
- `team-stats.sql` → `data/team-stats.sql`
- `generate-player-stats.py` → `scripts/generate-player-stats.py`
- `generate-team-stats.py` → `scripts/generate-team-stats.py`  
- `generate_player_names.py` → `scripts/generate_player_names.py`

### Files to Copy (they're already created in your workspace):
- `data_api.py` → `app.py`
- `data_api_requirements.txt` → `requirements.txt`
- `data_api_vercel.json` → `vercel.json`
- `DATA_API_README.md` → `README.md`

## Step 3: Deploy Data API

### Option A: Vercel (Recommended)
1. Push data repository to GitHub
2. Connect to Vercel
3. Deploy (vercel.json is already configured)
4. Note the deployed URL (e.g., `https://your-data-api.vercel.app`)

### Option B: Railway/Render
1. Connect repository to platform
2. Set start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
3. Deploy and note the URL

## Step 4: Update Main App Configuration

1. Set environment variable for API URL:
   ```bash
   # For local development
   export DATA_API_URL=http://localhost:8001
   
   # For production (use your deployed API URL)
   export DATA_API_URL=https://your-data-api.vercel.app
   ```

2. For Vercel deployment, add to vercel.json:
   ```json
   {
     "env": {
       "DATA_API_URL": "https://your-data-api.vercel.app"
     }
   }
   ```

## Step 5: Test the Setup

### Local Development
1. Start the data API:
   ```bash
   cd scotbot-data-api
   python app.py
   # API runs on http://localhost:8001
   ```

2. Start the main app:
   ```bash
   cd scotbot-transfer-tracker
   export DATA_API_URL=http://localhost:8001
   python app.py
   # App runs on http://localhost:8000
   ```

3. Test endpoints:
   - Autocomplete: http://localhost:8000/autocomplete?query=messi
   - Player: http://localhost:8000/transfers?query=messi
   - Team: http://localhost:8000/transfers?query=barcelona&type=team

### Production
1. Deploy both repositories
2. Update DATA_API_URL to point to deployed API
3. Test all functionality

## Step 6: Clean Up Main Repository

Once everything is working, you can remove these files from the main repository:
- `player-stats.sql`
- `team-stats.sql`
- `generate-player-stats.py`
- `generate-team-stats.py`
- `generate_player_names.py`
- `data_api.py`
- `data_api_requirements.txt`
- `data_api_vercel.json`
- `DATA_API_README.md`

## Benefits After Migration

1. **Scalability**: Data API can handle larger datasets without affecting main app
2. **Flexibility**: Can easily swap out data sources or add new APIs
3. **Performance**: Both services can be optimized independently
4. **Deployment**: Smaller, focused deployments
5. **Development**: Teams can work on different parts independently

## Future Expansion

To add new leagues/data sources:
1. Add new SQL files to `data/` directory in data repository
2. Update generation scripts in `scripts/`
3. Deploy data API
4. Main app automatically serves new data (no changes needed)

## Environment Variables

### Main App (`scotbot-transfer-tracker`)
- `DATA_API_URL`: URL of your deployed data API

### Data API (`scotbot-data-api`)
- No additional environment variables needed

## Troubleshooting

### Common Issues:
1. **API not responding**: Check DATA_API_URL is correct and API is deployed
2. **CORS errors**: Ensure CORSMiddleware is configured in data API
3. **404 errors**: Verify entity names exist in the data files
4. **Timeout errors**: Increase timeout in api_client.py if needed

### Debug Steps:
1. Check API health: `GET {DATA_API_URL}/health`
2. Test API directly: `GET {DATA_API_URL}/player/messi`
3. Check main app logs for API connection errors
4. Verify environment variables are set correctly
