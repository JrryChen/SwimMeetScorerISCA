# isca_point_scorer/apps/scoring/apps.py
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'isca_point_scorer.apps.scoring'