#!/usr/bin/env python3

# Import the FastAPI app
from data_api import app

# Export for Vercel
application = app

# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
