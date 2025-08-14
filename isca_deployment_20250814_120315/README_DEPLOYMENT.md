# ISCA Swim Scorer - FTP Deployment Guide

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

### Step 1: Upload to FTP Server

1. Upload this entire folder to `public_html/ISCA_red/`
2. The folder structure should look like:
   ```
   public_html/ISCA_red/
   └── isca_deployment_20250814_120315/
       ├── isca_swim_scorer/
       ├── docker-compose.ftp.yml
       ├── deploy_ftp.sh
       ├── README_DEPLOYMENT.md
       └── docker-compose.yml
   ```

### Step 2: IT Department Setup (Required)

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

### Step 3: Deploy Application

SSH into your server and run:

```bash
cd public_html/ISCA_red/isca_deployment_20250814_120315
chmod +x deploy_ftp.sh
./deploy_ftp.sh
```

## Configuration Files

### Production Docker Compose (`docker-compose.ftp.yml`)

- Uses port 8000 instead of 80 for shared hosting compatibility
- Includes Redis for caching and Celery for background tasks
- Configured for production with DEBUG=False

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
