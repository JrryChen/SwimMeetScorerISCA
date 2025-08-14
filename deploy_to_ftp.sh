#!/bin/bash

echo "=== Preparing ISCA Swim Scorer for FTP Deployment ==="

# Create deployment directory
DEPLOY_DIR="isca_deployment_$(date +%Y%m%d_%H%M%S)"
mkdir -p $DEPLOY_DIR

# Copy necessary files
echo "📁 Copying application files..."
cp -r isca_swim_scorer $DEPLOY_DIR/
cp docker-compose.prod.yml $DEPLOY_DIR/docker-compose.yml
cp deploy.sh $DEPLOY_DIR/
cp -r SampleMeetResults $DEPLOY_DIR/ 2>/dev/null || true

# Create a simple deployment guide
cat > $DEPLOY_DIR/README_DEPLOYMENT.md << 'EOF'
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
EOF

# Create a production settings override
cat > $DEPLOY_DIR/isca_swim_scorer/isca_swim_scorer/production_settings.py << 'EOF'
"""
Production settings override for ISCA Swim Scorer
"""
import os
from .settings import *

# Production settings
DEBUG = False
ALLOWED_HOSTS = ['ISCA.red', 'localhost', '127.0.0.1']

# Database - using SQLite for simplicity
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Static files
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_URL = '/static/'

# Media files
MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'

# Security
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
        },
    },
    'root': {
        'handlers': ['file'],
        'level': 'INFO',
    },
}

# Create logs directory
os.makedirs(BASE_DIR / 'logs', exist_ok=True)
EOF

# Create a simplified docker-compose for FTP deployment
cat > $DEPLOY_DIR/docker-compose.ftp.yml << 'EOF'
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
EOF

# Create a deployment script for FTP
cat > $DEPLOY_DIR/deploy_ftp.sh << 'EOF'
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

# Create superuser if needed (uncomment if needed)
# echo "👤 Creating superuser..."
# docker exec -it isca-django-ftp python manage.py createsuperuser

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
EOF

chmod +x $DEPLOY_DIR/deploy_ftp.sh

echo "✅ Deployment package created: $DEPLOY_DIR"
echo ""
echo "📋 Next steps:"
echo "1. Upload the '$DEPLOY_DIR' folder to your FTP server at: public_html/ISCA_red/"
echo "2. Contact your IT department to:"
echo "   - Create the .docker directory"
echo "   - Set up container mount points"
echo "   - Configure reverse proxy from port 8000 to port 80"
echo "   - Set up SSL certificate"
echo "3. SSH into your server and run: cd $DEPLOY_DIR && ./deploy_ftp.sh"
echo ""
echo "📁 Files included in deployment package:"
ls -la $DEPLOY_DIR/
