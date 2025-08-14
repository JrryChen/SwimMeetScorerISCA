# ISCA Swim Scorer

A Django-based web application for scoring swim meets, designed to integrate with the ISCA (International Swimming Coaches Association) website.

## Features

- Swim meet scoring and results management
- File upload processing for meet results
- REST API for integration with external systems
- Background task processing with Celery
- Redis-based caching and task queuing
- Docker containerization for easy deployment

## Prerequisites

Before running this project locally, ensure you have the following installed:

- **Docker** and **Docker Compose**
- **Git** (for cloning the repository)

## Quick Start with Docker

The easiest way to run the project locally is using Docker Compose:

### 1. Clone the Repository

```bash
git clone <repository-url>
cd SwimMeetScorerISCA
```

### 2. Start the Application

```bash
docker-compose up --build
```

This command will:

- Build the Django application container
- Start Redis for background tasks
- Start the Django development server on port 80
- Start Celery worker for background task processing

### 3. Create Superuser (Required for Admin Access)

To access the Django admin interface, you'll need to create a superuser account:

```bash
docker-compose exec django-app-isca python manage.py createsuperuser
```

Follow the prompts to set up your admin username, email, and password.

### 4. Access the Application

Open your browser and navigate to:

- **Main Application**: http://localhost
- **Admin Interface**: http://localhost/admin

### 5. Stop the Application

```bash
docker-compose down
```

## Project Structure

```
isca_swim_scorer/
├── core/                 # Core application functionality
├── meets/               # Meet management
├── scoring/             # Scoring algorithms
├── uploads/             # File upload handling
├── api/                 # REST API endpoints
├── templates/           # HTML templates
├── media/               # User-uploaded files
├── tests/               # Test files
├── manage.py            # Django management script
├── requirements.txt     # Python dependencies
├── Dockerfile          # Docker configuration
└── isca_swim_scorer/   # Django project settings
    ├── settings.py     # Django settings
    ├── urls.py         # URL configuration
    ├── celery.py       # Celery configuration
    └── wsgi.py         # WSGI configuration
```

## Key Dependencies

- **Django 4.2.10**: Web framework
- **Django REST Framework**: API development
- **Celery 5.5.2**: Background task processing
- **Redis 6.0.0**: Message broker and caching
- **hytek-parser**: Swim meet file parsing
- **openpyxl**: Excel file processing
- **numpy & scipy**: Mathematical computations

## Development Workflow

### Running Tests

```bash
docker-compose exec django-app-isca python manage.py test
```

### Database Management

```bash
# Create migrations
docker-compose exec django-app-isca python manage.py makemigrations

# Apply migrations
docker-compose exec django-app-isca python manage.py migrate

# Reset database (development only)
docker-compose exec django-app-isca python manage.py flush
```

## Troubleshooting

### Common Issues

1. **Port 80 already in use**

   - Change the port in `docker-compose.yml` or stop other services using port 80

2. **Redis connection errors**

   - Ensure the Redis container is running: `docker-compose ps`
   - Check container logs: `docker-compose logs redis-app-isca`

3. **Permission errors with media files**

   - The Docker setup handles permissions automatically

4. **Celery worker not starting**
   - Check container logs: `docker-compose logs celery-app-isca`
   - Ensure Redis container is running

## Production Deployment

For production deployment, refer to:

- `DEPLOYMENT_GUIDE.md` - General deployment instructions
- `FTP_DEPLOYMENT_GUIDE.md` - FTP-specific deployment
- `docker-compose.prod.yml` - Production Docker configuration

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

This project is proprietary software for ISCA (International Swimming Coaches Association).

## Support

For technical support or questions, please contact the development team or refer to the project documentation.
