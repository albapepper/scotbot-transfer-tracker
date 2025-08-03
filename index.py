#!/usr/bin/env python3

# Import the Flask app
from app import app

# Export for Vercel/WSGI
application = app

# For local development
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
