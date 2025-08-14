# ISCA Website Integration Guide

This guide explains how to seamlessly integrate the SwimMeetScorer webapp into the ISCA website at swimisca.org.

## Integration Options

### Option 1: Iframe Embedding (Recommended)

The easiest way to integrate the app is using an iframe. This maintains the existing ISCA website structure while adding the scoring functionality.

#### HTML Code for ISCA Website:

```html
<!-- Add this to any page on swimisca.org -->
<div class="isca-scorer-container">
    <iframe 
        src="https://scorer.swimisca.org/uploads/iframe/" 
        width="100%" 
        height="800px" 
        frameborder="0" 
        style="border: none; border-radius: 15px; box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);">
        <p>Your browser does not support iframes. Please <a href="https://scorer.swimisca.org">click here</a> to access the ISCA Meet Scorer.</p>
    </iframe>
</div>

<style>
.isca-scorer-container {
    margin: 2rem 0;
    padding: 0;
}

@media (max-width: 768px) {
    .isca-scorer-container iframe {
        height: 900px;
    }
}
</style>
```

#### Benefits:
- No changes to existing ISCA website
- Maintains ISCA branding and navigation
- Easy to maintain and update
- Responsive design

### Option 2: Direct Subdomain Integration

Deploy the app at a subdomain like `scorer.swimisca.org` or `meets.swimisca.org`.

#### DNS Configuration:
```
scorer.swimisca.org A 100.27.220.135
```

#### Benefits:
- Standalone application
- Full control over design
- Better SEO
- Can be linked from main site

## Deployment Configuration

### 1. Docker Deployment (Recommended)

Update the `docker-compose.yml` for production:

```yaml
version: "3.8"

services:
  redis-app-isca:
    image: redis:latest
    restart: unless-stopped

  django-app-isca:
    image: jrrychen/isca-django:latest
    container_name: django-app-isca
    build:
      context: ./isca_swim_scorer
    command: gunicorn isca_swim_scorer.wsgi:application --bind 0.0.0.0:8000 --workers 3
    volumes:
      - ./isca_swim_scorer:/usr/src/app
      - static_volume:/usr/src/app/staticfiles
      - media_volume:/usr/src/app/media
    ports:
      - "8000:8000"
    environment:
      - DEBUG=False
      - ALLOWED_HOSTS=scorer.swimisca.org,swimisca.org,www.swimisca.org,100.27.220.135
      - SECRET_KEY=${SECRET_KEY}
      - DATABASE_URL=${DATABASE_URL}
    depends_on:
      - redis-app-isca
    restart: unless-stopped

  celery-app-isca:
    image: jrrychen/isca-celery:latest
    container_name: celery-app-isca
    build:
      context: ./isca_swim_scorer
    command: celery --app=isca_swim_scorer worker --loglevel=info
    volumes:
      - ./isca_swim_scorer:/usr/src/app
      - media_volume:/usr/src/app/media
    environment:
      - DEBUG=False
      - ALLOWED_HOSTS=scorer.swimisca.org,swimisca.org,www.swimisca.org,100.27.220.135
      - SECRET_KEY=${SECRET_KEY}
      - DATABASE_URL=${DATABASE_URL}
    depends_on:
      - redis-app-isca
      - django-app-isca
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    container_name: nginx-isca
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - static_volume:/usr/src/app/staticfiles
      - media_volume:/usr/src/app/media
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - django-app-isca
    restart: unless-stopped

volumes:
  static_volume:
  media_volume:
```

### 2. Nginx Configuration

Create `nginx.conf`:

```nginx
events {
    worker_connections 1024;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    upstream django {
        server django-app-isca:8000;
    }

    server {
        listen 80;
        server_name scorer.swimisca.org;
        
        # Redirect HTTP to HTTPS
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name scorer.swimisca.org;

        # SSL Configuration
        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;

        client_max_body_size 50M;

        # Add headers for iframe embedding
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header Content-Security-Policy "frame-ancestors 'self' https://swimisca.org https://www.swimisca.org" always;

        location / {
            proxy_pass http://django;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_redirect off;
        }

        location /static/ {
            alias /usr/src/app/staticfiles/;
        }

        location /media/ {
            alias /usr/src/app/media/;
        }
    }
}
```

## Integration Steps

### Step 1: Update ISCA Website

1. Choose a page where you want to embed the scorer (e.g., a new "Meet Scoring" page)
2. Add the iframe code to the page
3. Test the integration

### Step 2: DNS Configuration

If using subdomain approach:
1. Add DNS A record: `scorer.swimisca.org` → `100.27.220.135`
2. Configure SSL certificate for the subdomain

### Step 3: App Deployment

1. Deploy the updated app with ISCA branding
2. Configure environment variables
3. Test all functionality

### Step 4: WordPress Integration (Advanced)

For tighter integration with WordPress:

```php
// Add to your WordPress theme's functions.php
function isca_scorer_shortcode($atts) {
    $atts = shortcode_atts(array(
        'height' => '800',
        'width' => '100%'
    ), $atts, 'isca_scorer');

    return '<div class="isca-scorer-wrapper">
        <iframe 
            src="https://scorer.swimisca.org/uploads/iframe/" 
            width="' . esc_attr($atts['width']) . '" 
            height="' . esc_attr($atts['height']) . 'px" 
            frameborder="0" 
            style="border: none; border-radius: 15px; box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);">
        </iframe>
    </div>';
}
add_shortcode('isca_scorer', 'isca_scorer_shortcode');
```

Usage in WordPress posts/pages:
```
[isca_scorer height="900"]
```

## Available Endpoints

- `/uploads/` - Main upload interface (full page)
- `/uploads/iframe/` - Iframe-friendly upload interface
- `/uploads/status/` - Check upload status
- `/uploads/admin/` - Admin panel (authentication required)

## Customization

The app now includes:
- ISCA official branding and colors
- Links to main ISCA website
- Footer with ISCA contact information
- Responsive design for all devices
- Professional styling matching ISCA website

## Testing

Test the integration:

1. Upload a test HY3 file
2. Verify processing works
3. Check results download
4. Test on mobile devices
5. Verify iframe embedding works properly

## Support

For technical support or customization requests:
- Email: webmaster-team@swimisca.com
- Phone: 540-792-2020

## Security Considerations

- CSRF protection enabled
- File type validation
- Size limits enforced
- CORS configured for ISCA domains only
- Secure iframe embedding headers

This integration provides a professional, seamless experience for ISCA members while maintaining the organization's branding and website structure. 