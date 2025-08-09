# Deploy Data API to Vercel (PowerShell version)
# This script helps deploy your data API as a separate Vercel project

Write-Host "🚀 Deploying Scotbot Data API to Vercel..." -ForegroundColor Green

# Create a temporary directory for the API deployment
if (Test-Path "api-deploy") {
    Remove-Item -Recurse -Force "api-deploy"
}
New-Item -ItemType Directory -Name "api-deploy"
Set-Location "api-deploy"

# Copy necessary files for the API
Copy-Item "../data_api.py" "."
Copy-Item "../api_index.py" "index.py"
Copy-Item "../api_vercel.json" "vercel.json"
Copy-Item "../api_requirements.txt" "requirements.txt"

# Copy the data directory
Copy-Item -Recurse "../data" "."

Write-Host "📁 Files prepared for deployment:" -ForegroundColor Yellow
Get-ChildItem

Write-Host ""
Write-Host "🔧 Next steps:" -ForegroundColor Cyan
Write-Host "1. Run: vercel --prod"
Write-Host "2. Follow the prompts to deploy"
Write-Host "3. Copy the deployment URL"
Write-Host "4. Update your main app's DATA_API_URL environment variable"

Write-Host ""
Write-Host "💡 Example commands:" -ForegroundColor Magenta
Write-Host "   cd api-deploy"
Write-Host "   vercel --prod"
Write-Host ""
Write-Host "   # After deployment, update main app:"
Write-Host "   # `$env:DATA_API_URL='https://your-api-url.vercel.app'"
