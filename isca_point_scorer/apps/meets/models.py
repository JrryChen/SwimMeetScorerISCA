from django.db import models
from django.utils.text import slugify

from isca_point_scorer.apps.core.models import TimeStampedModel, Gender, Course, Stroke

class Meet(TimeStampedModel):
    """
    Represents a swim meet.
    """
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    location = models.CharField(max_length=255, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    course = models.CharField(max_length=3, choices=Course.choices, default=Course.SHORT_COURSE_YARDS)
    is_published = models.BooleanField(default=False)
    is_processed = models.BooleanField(default=False)
    processing_errors = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-start_date']
        
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)