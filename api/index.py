from app import app

# This is needed for Vercel's serverless function
def handler(request):
    return app(request.environ, request.start_response)
