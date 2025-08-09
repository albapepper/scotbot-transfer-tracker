#!/bin/bash

# Deploy Data API to Vercel
# This script helps deploy your data API as a separate Vercel project

echo "🚀 Deploying Scotbot Data API to Vercel..."

# Create a temporary directory for the API deployment
mkdir -p api-deploy
cd api-deploy

# Copy necessary files for the API
cp ../data_api.py .
cp ../api_index.py index.py
cp ../api_vercel.json vercel.json
cp ../api_requirements.txt requirements.txt

# Copy the data directory
cp -r ../data .

echo "📁 Files prepared for deployment:"
ls -la

echo ""
echo "🔧 Next steps:"
echo "1. Run: vercel --prod"
echo "2. Follow the prompts to deploy"
echo "3. Copy the deployment URL"
echo "4. Update your main app's DATA_API_URL environment variable"

echo ""
echo "💡 Example commands:"
echo "   cd api-deploy"
echo "   vercel --prod"
echo ""
echo "   # After deployment, update main app:"
echo "   # export DATA_API_URL=https://your-api-url.vercel.app"
