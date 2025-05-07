from django.db import models
from django.utils.translation import gettext_lazy as _
# Create your models here.

class TimeStampedModel(models.Model):
    """
    An abstract base class model that provides self-updating
    'created_at' and 'updated_at' fields.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class Gender(models.TextChoices):
    MALE = 'M', _('Male')
    FEMALE = 'F', _('Female')
    MIXED = 'X', _('Mixed')
    UNKNOWN = 'U', _('Unknown')

class Course(models.TextChoices):
    SHORT_COURSE_YARDS = 'SCY', _('Short Course Yards')
    LONG_COURSE_METERS = 'LCM', _('Long Course Meters')
    SHORT_COURSE_METERS = 'SCM', _('Short Course Meters')

class Stroke(models.TextChoices):
    FREESTYLE = 'FR', _('Freestyle')
    BACKSTROKE = 'BK', _('Backstroke')
    BREASTSTROKE = 'BR', _('Breaststroke')
    BUTTERFLY = 'FL', _('Butterfly')
    IM = 'IM', _('Individual Medley')
    MEDLEY_RELAY = 'MR', _('Medley Relay')
    FREESTYLE_RELAY = 'FRR', _('Freestyle Relay')
    
