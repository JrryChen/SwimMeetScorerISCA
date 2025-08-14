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

