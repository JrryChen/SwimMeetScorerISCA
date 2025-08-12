# ISCA Swim Scorer - Shared Hosting Deployment Guide

## Overview
This guide explains how to deploy the ISCA Swim Scorer Django application on pair.com shared hosting with Docker access.

## Prerequisites
- Access to `public_html/isca_red` folder
- Docker installed on the server (confirmed available)
- FTP access to upload files

## Deployment Strategy

### Option 1: Docker Compose (Recommended)
Since Docker is available, we'll use a simplified Docker Compose setup.

### Option 2: Standalone Docker Container
If Docker Compose isn't available, we'll use individual Docker containers.

## Step-by-Step Deployment

### 1. Prepare Your Local Files
```bash
# Create a deployment package
mkdir isca_deployment
cp -r isca_swim_scorer isca_deployment/
cp docker-compose.yml isca_deployment/
cp Dockerfile isca_deployment/
```

### 2. Upload to Server
Upload the entire `isca_deployment` folder to your `public_html/isca_red` directory via FTP.

### 3. SSH into Server (if available)
```bash
ssh your-username@your-domain.com
cd public_html/isca_red/isca_deployment
```

### 4. Build and Run with Docker
```bash
# Build the Docker image
docker build -t isca-swim-scorer ./isca_swim_scorer

# Run the container
docker run -d \
  --name isca-app \
  -p 8080:8000 \
  -v $(pwd)/isca_swim_scorer:/usr/src/app \
  -e DEBUG=False \
  -e ALLOWED_HOSTS=your-domain.com,www.your-domain.com \
  -e SECRET_KEY=your-secret-key-here \
  isca-swim-scorer
```

### 5. Alternative: Docker Compose
```bash
# Modify docker-compose.yml for production
docker-compose -f docker-compose.prod.yml up -d
```

## Configuration Files

### Production Docker Compose
Create `docker-compose.prod.yml`:
```yaml
version: "3.8"
services:
  django-app-isca:
    build:
      context: ./isca_swim_scorer
    container_name: isca-django-prod
    command: gunicorn isca_swim_scorer.wsgi:application --bind 0.0.0.0:8000
    volumes:
      - ./isca_swim_scorer:/usr/src/app
      - media_volume:/usr/src/app/media
    ports:
      - "8080:8000"
    environment:
      - DEBUG=False
      - ALLOWED_HOSTS=your-domain.com,www.your-domain.com
      - SECRET_KEY=your-secret-key-here
    restart: unless-stopped

volumes:
  media_volume:
```

### Production Settings
Modify `isca_swim_scorer/isca_swim_scorer/settings.py`:
```python
DEBUG = False
ALLOWED_HOSTS = ['your-domain.com', 'www.your-domain.com']

# Use SQLite for simplicity (or configure your database)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Static files
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_URL = '/static/'
```

## Domain Configuration

### Option 1: Subdomain
- Create subdomain: `scorer.your-domain.com`
- Point to port 8080

### Option 2: Subdirectory
- Access via: `your-domain.com/isca_red/isca_deployment`
- Configure reverse proxy if needed

## Database Setup
```bash
# Run migrations
docker exec isca-app python manage.py migrate

# Create superuser
docker exec -it isca-app python manage.py createsuperuser

# Collect static files
docker exec isca-app python manage.py collectstatic --noinput
```

## Monitoring and Maintenance
```bash
# Check container status
docker ps

# View logs
docker logs isca-app

# Restart container
docker restart isca-app

# Update application
docker-compose down
docker-compose up -d --build
```

## Troubleshooting

### Common Issues:
1. **Port conflicts**: Change port mapping from 8080:8000 to 8081:8000
2. **Permission issues**: Ensure proper file permissions
3. **Database errors**: Check if SQLite file is writable
4. **Static files**: Run collectstatic command

### Logs:
```bash
docker logs isca-app
docker logs isca-app --tail 100
```

## Security Considerations
- Change default SECRET_KEY
- Set DEBUG=False in production
- Configure proper ALLOWED_HOSTS
- Use HTTPS if available
- Regular backups of database

## Backup Strategy
```bash
# Backup database
docker exec isca-app python manage.py dumpdata > backup.json

# Backup media files
tar -czf media_backup.tar.gz ./isca_swim_scorer/media/
```

## Performance Optimization
- Enable Django caching
- Use CDN for static files
- Optimize database queries
- Monitor resource usage 