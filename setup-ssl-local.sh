#!/bin/bash

echo "=== Setting up SSL for ISCA Swim Scorer (Local/Development) ==="

# Create SSL directory
mkdir -p ssl

# Check if we're in development mode
if [ "$1" = "dev" ]; then
    echo "🔧 Development mode: Creating self-signed certificates..."
    
    # Create self-signed certificate for development
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout ssl/privkey.pem \
        -out ssl/fullchain.pem \
        -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
    
    echo "✅ Self-signed certificates created for development!"
    echo "⚠️  Note: Browsers will show security warnings for self-signed certificates"
else
    echo "🌐 Production mode: Please provide SSL certificates"
    echo ""
    echo "To set up SSL certificates:"
    echo "1. Obtain SSL certificates for your domains"
    echo "2. Place them in the ssl/ directory:"
    echo "   - ssl/fullchain.pem (certificate)"
    echo "   - ssl/privkey.pem (private key)"
    echo ""
    echo "Or run with development mode: ./setup-ssl-local.sh dev"
fi

echo ""
echo "🚀 Start the application with: docker-compose up -d"
echo "📱 Access via:"
echo "   - HTTP:  http://localhost"
echo "   - HTTPS: https://localhost (if certificates are set up)"
