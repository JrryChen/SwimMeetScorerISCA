# ISCA Swim Scorer - FTP Server Deployment Guide

## Overview

This guide explains how to deploy the ISCA Swim Scorer Django application on your FTP server at `public_html/ISCA_red` with Docker container mount points.

## Prerequisites

- ✅ FTP access to `public_html/ISCA_red` (confirmed)
- ✅ Docker installed on server (confirmed by IT)
- ✅ SSH access to server (for deployment commands)

## Understanding Container Mount Points

The IT department mentioned the `.docker` folder and container mount points. Here's what this means:

### What is the .docker directory?

- This is where Docker stores container data, volumes, and configuration
- IT needs to create this directory and configure proper permissions
- Your application files will be mounted into containers from this location

### Required Mount Points

Your application needs these volume mounts:

1. **Application Code**: `./isca_swim_scorer:/usr/src/app`
2. **Media Files**: `media_volume:/usr/src/app/media`
3. **Redis Data**: `redis_data:/data`

## Step-by-Step Deployment

### Step 1: Prepare Deployment Package

Run the deployment preparation script:

```bash
chmod +x deploy_to_ftp.sh
./deploy_to_ftp.sh
```

This creates a timestamped deployment package with all necessary files.

### Step 2: Upload to FTP Server

1. Upload the entire deployment folder to `public_html/ISCA_red/`
2. The folder structure should look like:
   ```
   public_html/ISCA_red/
   └── isca_deployment_YYYYMMDD_HHMMSS/
       ├── isca_swim_scorer/
       ├── docker-compose.ftp.yml
       ├── deploy_ftp.sh
       ├── README_DEPLOYMENT.md
       └── SampleMeetResults/
   ```

### Step 3: IT Department Setup (Required)

Contact your IT department to:

1. **Create .docker directory**:

   ```bash
   mkdir -p /path/to/.docker/isca_swim_scorer
   chown -R your-user:your-group /path/to/.docker/isca_swim_scorer
   ```

2. **Configure container mount points**:

   - Map your FTP directory to the .docker directory
   - Ensure proper permissions for volume mounts
   - Set up network access for containers

3. **Configure reverse proxy**:
   - Route traffic from port 80 to port 8000
   - Set up SSL certificate for HTTPS
   - Configure domain routing for ISCA.red

### Step 4: Deploy Application

SSH into your server and run:

```bash
cd public_html/ISCA_red/isca_deployment_YYYYMMDD_HHMMSS
chmod +x deploy_ftp.sh
./deploy_ftp.sh
```

## Configuration Files

### Production Docker Compose (`docker-compose.ftp.yml`)

```yaml
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
      - "8000:8000" # Using port 8000 for shared hosting
    environment:
      - DEBUG=False
      - ALLOWED_HOSTS=localhost,127.0.0.1,ISCA.red
      - SECRET_KEY=1231251231421
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
```

## IT Department Requirements

### 1. Container Mount Points

The IT department needs to ensure these mount points work:

- **Application Code**: Your uploaded files must be accessible to containers
- **Media Volume**: Persistent storage for uploaded files
- **Redis Data**: Persistent storage for cache and sessions

### 2. Network Configuration

- **Port Mapping**: Route external port 80 to container port 8000
- **SSL/TLS**: Configure HTTPS certificate for ISCA.red
- **Domain Routing**: Point ISCA.red to your application

### 3. File Permissions

```bash
# Set proper permissions for Docker volumes
chmod -R 755 /path/to/.docker/isca_swim_scorer
chmod -R 777 /path/to/.docker/isca_swim_scorer/media
chmod -R 777 /path/to/.docker/isca_swim_scorer/logs
```

## Post-Deployment Setup

### 1. Create Superuser

```bash
docker exec -it isca-django-ftp python manage.py createsuperuser
```

### 2. Verify Application

- Visit: https://ISCA.red
- Check admin interface: https://ISCA.red/admin
- Verify file uploads work

### 3. Monitor Logs

```bash
# View Django logs
docker logs isca-django-ftp

# View Celery logs
docker logs isca-celery-ftp

# View Redis logs
docker logs isca-redis-ftp
```

## Troubleshooting

### Common Issues

1. **Permission Denied**:

   ```bash
   chmod -R 755 .
   chmod -R 777 media logs
   ```

2. **Port Already in Use**:

   - Change port mapping in docker-compose.ftp.yml
   - Contact IT to configure reverse proxy

3. **Container Won't Start**:

   ```bash
   docker logs isca-django-ftp
   docker-compose -f docker-compose.ftp.yml down
   docker-compose -f docker-compose.ftp.yml up -d --build
   ```

4. **Database Migration Errors**:
   ```bash
   docker exec isca-django-ftp python manage.py migrate --run-syncdb
   ```

### IT Department Contact Information

When contacting IT, provide them with:

- This deployment guide
- The docker-compose.ftp.yml file
- Requirements for .docker directory setup
- Port mapping requirements (80 → 8000)
- SSL certificate setup for ISCA.red

## Security Considerations

1. **Change Default Secret Key**:

   - Generate a new SECRET_KEY
   - Update in docker-compose.ftp.yml

2. **Environment Variables**:

   - Set DEBUG=False (already configured)
   - Configure proper ALLOWED_HOSTS

3. **File Permissions**:
   - Ensure media directory is writable
   - Restrict access to sensitive files

## Backup Strategy

```bash
# Backup database
docker exec isca-django-ftp python manage.py dumpdata > backup.json

# Backup media files
tar -czf media_backup.tar.gz ./isca_swim_scorer/media/

# Backup entire application
tar -czf app_backup.tar.gz ./isca_swim_scorer/
```

## Maintenance

### Regular Updates

```bash
# Pull latest changes
git pull origin main

# Rebuild and restart containers
docker-compose -f docker-compose.ftp.yml down
docker-compose -f docker-compose.ftp.yml up -d --build

# Run migrations
docker exec isca-django-ftp python manage.py migrate
```

### Monitoring

- Check container status: `docker ps`
- Monitor logs: `docker logs isca-django-ftp`
- Check disk space: `df -h`
- Monitor memory usage: `docker stats`
