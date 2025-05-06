INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party apps
    'rest_framework',
    'django_filters',
    
    # Local apps
    'isca_point_scorer.apps.core.apps.CoreConfig',
    'isca_point_scorer.apps.meets.apps.MeetsConfig',
    'isca_point_scorer.apps.scoring.apps.ScoringConfig',
    'isca_point_scorer.apps.uploads.apps.UploadsConfig',
    'isca_point_scorer.apps.api.apps.ApiConfig',
]