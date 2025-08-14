# PowerShell script to prepare ISCA Swim Scorer for FTP deployment

Write-Host "=== Preparing ISCA Swim Scorer for FTP Deployment ===" -ForegroundColor Green

# Create deployment directory with timestamp
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$deployDir = "isca_deployment_$timestamp"
New-Item -ItemType Directory -Path $deployDir -Force | Out-Null

Write-Host "📁 Copying application files..." -ForegroundColor Yellow

# Copy necessary files
Copy-Item -Path "isca_swim_scorer" -Destination $deployDir -Recurse -Force
Copy-Item -Path "docker-compose.prod.yml" -Destination "$deployDir/docker-compose.yml" -Force
Copy-Item -Path "deploy.sh" -Destination $deployDir -Force

# Copy SampleMeetResults if it exists
if (Test-Path "SampleMeetResults") {
    Copy-Item -Path "SampleMeetResults" -Destination $deployDir -Recurse -Force
}

# Create deployment guide
$readmeContent = @"
# ISCA Swim Scorer - FTP Deployment

## Quick Start
1. Upload this entire folder to your FTP server at: public_html/ISCA_red/
2. SSH into your server and navigate to the uploaded directory
3. Run: chmod +x deploy.sh && ./deploy.sh

## Files Structure
- isca_swim_scorer/ - Main Django application
- docker-compose.yml - Production Docker configuration
- deploy.sh - Deployment script
- SampleMeetResults/ - Sample data files

## Container Mount Points
The IT department will need to:
1. Create a .docker directory in your hosting environment
2. Mount the following volumes:
   - ./isca_swim_scorer:/usr/src/app (application code)
   - media_volume:/usr/src/app/media (uploaded files)
   - redis_data:/data (Redis database)

## Environment Variables
- DEBUG=False (production mode)
- ALLOWED_HOSTS=ISCA.red,localhost,127.0.0.1
- SECRET_KEY=1231251231421 (change this in production)

## Access
- Main application: https://ISCA.red
- Admin interface: https://ISCA.red/admin
"@

Set-Content -Path "$deployDir/README_DEPLOYMENT.md" -Value $readmeContent

# Create simplified docker-compose for FTP deployment
$dockerComposeFtp = @"
version: "3.8"

services:
  redis-app-isca:
    image: redis:latest
    container_name: isca-redis-ftp
    restart: unless-stopped
    volumes:
      - redis_data:/data

  django-app-isca:
    build:
      context: ./isca_swim_scorer
    container_name: isca-django-ftp
    command: gunicorn isca_swim_scorer.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 120
    volumes:
      - ./isca_swim_scorer:/usr/src/app
      - media_volume:/usr/src/app/media
    ports:
      - "8000:8000"  # Using port 8000 instead of 80 for shared hosting
    environment:
      - DEBUG=False
      - ALLOWED_HOSTS=localhost,127.0.0.1,ISCA.red
      - SECRET_KEY=1231251231421
      - X_FRAME_OPTIONS=SAMEORIGIN
    depends_on:
      - redis-app-isca
    restart: unless-stopped

  celery-app-isca:
    build:
      context: ./isca_swim_scorer
    container_name: isca-celery-ftp
    command: celery --app=isca_swim_scorer worker --loglevel=info
    volumes:
      - ./isca_swim_scorer:/usr/src/app
      - media_volume:/usr/src/app/media
    environment:
      - DEBUG=False
      - ALLOWED_HOSTS=localhost,127.0.0.1,ISCA.red
      - SECRET_KEY=1231251231421
    depends_on:
      - redis-app-isca
      - django-app-isca
    restart: unless-stopped

volumes:
  redis_data:
  media_volume:
"@

Set-Content -Path "$deployDir/docker-compose.ftp.yml" -Value $dockerComposeFtp

# Create deployment script for FTP
$deployFtpScript = @"
#!/bin/bash
echo "=== Deploying ISCA Swim Scorer on FTP Server ==="

# Create necessary directories
mkdir -p logs media staticfiles

# Set proper permissions
chmod -R 755 .
chmod -R 777 media logs

# Stop existing containers
docker-compose -f docker-compose.ftp.yml down 2>/dev/null || true

# Build and start containers
echo "🔨 Building and starting containers..."
docker-compose -f docker-compose.ftp.yml up -d --build

# Wait for containers to be ready
echo "⏳ Waiting for containers to start..."
sleep 20

# Run migrations
echo "🗄️  Running database migrations..."
docker exec isca-django-ftp python manage.py migrate

# Collect static files
echo "📁 Collecting static files..."
docker exec isca-django-ftp python manage.py collectstatic --noinput

# Check container status
echo "🔍 Checking container status..."
docker ps --filter "name=isca-"

echo "✅ Deployment complete!"
echo "🌐 Your application should be available at: https://ISCA.red:8000"
echo ""
echo "📊 Container Status:"
echo "  - Django: https://ISCA.red:8000"
echo "  - Redis: Running (internal)"
echo "  - Celery: Running (background tasks)"
echo ""
echo "📝 Next steps:"
echo "  1. Contact IT to configure reverse proxy from port 8000 to port 80"
echo "  2. Set up SSL certificate for HTTPS"
echo "  3. Configure domain routing to point to your application"
"@

Set-Content -Path "$deployDir/deploy_ftp.sh" -Value $deployFtpScript

Write-Host "✅ Deployment package created: $deployDir" -ForegroundColor Green
Write-Host ""
Write-Host "📋 Next steps:" -ForegroundColor Cyan
Write-Host "1. Upload the '$deployDir' folder to your FTP server at: public_html/ISCA_red/" -ForegroundColor White
Write-Host "2. Contact your IT department to:" -ForegroundColor White
Write-Host "   - Create the .docker directory" -ForegroundColor White
Write-Host "   - Set up container mount points" -ForegroundColor White
Write-Host "   - Configure reverse proxy from port 8000 to port 80" -ForegroundColor White
Write-Host "   - Set up SSL certificate" -ForegroundColor White
Write-Host "3. SSH into your server and run: cd $deployDir && ./deploy_ftp.sh" -ForegroundColor White
Write-Host ""
Write-Host "📁 Files included in deployment package:" -ForegroundColor Cyan
Get-ChildItem -Path $deployDir | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
