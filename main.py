from app import app
import os

# For Vercel deployment - ensure we're in the right directory
if os.getcwd() != os.path.dirname(os.path.abspath(__file__)):
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

# This is the WSGI application entry point
application = app

if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
