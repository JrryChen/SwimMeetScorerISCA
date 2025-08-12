#!/bin/bash
echo "=== Deploying ISCA Swim Scorer ==="

# Stop existing containers
docker-compose -f docker-compose.prod.yml down 2>/dev/null || true

# Start all services using pre-built images (Django, Redis, Celery)
docker-compose -f docker-compose.prod.yml up -d

# Wait for containers to be ready
echo "⏳ Waiting for containers to start..."
sleep 15

# Run migrations
echo "🗄️  Running database migrations..."
docker exec isca-django-prod python manage.py migrate

# Note: No static files to collect (using CDN for Bootstrap)

# Check if all containers are running
echo "🔍 Checking container status..."
docker ps --filter "name=isca-"

echo "✅ Deployment complete!"
echo "🌐 Your application should be available at: http://ISCA.red"
echo ""
echo "📊 Container Status:"
echo "  - Django: http://ISCA.red"
echo "  - Redis: Running (internal)"
echo "  - Celery: Running (background tasks)"
