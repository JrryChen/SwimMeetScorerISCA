#!/bin/bash

echo "=== Setting up SSL for ISCA Swim Scorer ==="

# Create SSL directory
mkdir -p ssl

# Check if certbot is available
if command -v certbot &> /dev/null; then
    echo "✅ Certbot found, obtaining SSL certificate..."
    
    # Stop nginx temporarily
    docker-compose -f docker-compose.prod.ssl.yml stop nginx
    
    # Obtain certificate
    certbot certonly --standalone \
        --email your-email@example.com \
        --agree-tos \
        --no-eff-email \
        -d ISCA.red \
        -d www.ISCA.red
    
    # Copy certificates to ssl directory
    sudo cp /etc/letsencrypt/live/ISCA.red/fullchain.pem ssl/
    sudo cp /etc/letsencrypt/live/ISCA.red/privkey.pem ssl/
    sudo chown $USER:$USER ssl/*
    
    echo "✅ SSL certificates obtained and copied!"
else
    echo "⚠️  Certbot not found. Please install it or obtain certificates manually."
    echo "For manual setup:"
    echo "1. Obtain SSL certificates for ISCA.red"
    echo "2. Place them in the ssl/ directory:"
    echo "   - ssl/fullchain.pem (certificate)"
    echo "   - ssl/privkey.pem (private key)"
fi

# Update nginx.conf with correct certificate paths
sed -i 's|ssl_certificate /etc/ssl/certs/your-domain.crt;|ssl_certificate /etc/ssl/fullchain.pem;|g' nginx.conf
sed -i 's|ssl_certificate_key /etc/ssl/private/your-domain.key;|ssl_certificate_key /etc/ssl/privkey.pem;|g' nginx.conf

echo "✅ SSL setup complete!"
echo "🚀 Start the application with: docker-compose -f docker-compose.prod.ssl.yml up -d"
