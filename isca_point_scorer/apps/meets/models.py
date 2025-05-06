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

class Team(TimeStampedModel):
    """
    Represents a swim team.
    """
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=10)
    short_name = models.CharField(max_length=50, blank=True)
    meet = models.ForeignKey(Meet, on_delete=models.CASCADE, related_name='teams')
    
    class Meta:
        ordering = ['name']
        unique_together = ['code', 'meet']
        
    def __str__(self):
        return self.name    

class Swimmer(TimeStampedModel):
    """
    Represents a swimmer who participates in meets.
    """
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=1, choices=Gender.choices)
    date_of_birth = models.DateField(null=True, blank=True)
    age = models.IntegerField(null=True, blank=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='swimmers')
    meet = models.ForeignKey(Meet, on_delete=models.CASCADE, related_name='swimmers')
    
    # Hytek-specific identifiers
    meet_id = models.CharField(max_length=20, blank=True)
    usa_swimming_id = models.CharField(max_length=20, blank=True)
    
    class Meta:
        ordering = ['last_name', 'first_name']
        unique_together = ['meet_id', 'meet']
        
    def __str__(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def full_name(self):
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"        
    
class Event(TimeStampedModel):
    """
    Represents an event in a swim meet.
    """
    meet = models.ForeignKey(Meet, on_delete=models.CASCADE, related_name='events')
    event_number = models.CharField(max_length=10)
    name = models.CharField(max_length=255)
    distance = models.IntegerField()
    stroke = models.CharField(max_length=2, choices=Stroke.choices)
    gender = models.CharField(max_length=1, choices=Gender.choices)
    is_relay = models.BooleanField(default=False)
    min_age = models.IntegerField(default=0)
    max_age = models.IntegerField(default=99)
    
    class Meta:
        ordering = ['event_number']
        unique_together = ['meet', 'event_number']
        
    def __str__(self):
        return f"{self.event_number} - {self.name}"
    
    @property
    def event_key(self):
        """Generate a unique key for lookup in point systems"""
        relay_prefix = "Relay " if self.is_relay else ""
        gender_text = "Men's" if self.gender == Gender.MALE else "Women's" if self.gender == Gender.FEMALE else "Mixed"
        return f"{gender_text} {relay_prefix}{self.distance} {self.get_stroke_display()} ({self.meet.get_course_display()})"
    
class Result(TimeStampedModel):
    """
    Represents a swimmer's result in an event.
    """
    swimmer = models.ForeignKey(Swimmer, on_delete=models.CASCADE, related_name='results')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='results')
    
    # Times in seconds
    seed_time = models.FloatField(null=True, blank=True)
    prelim_time = models.FloatField(null=True, blank=True)
    finals_time = models.FloatField(null=True, blank=True)
    
    # Places
    prelim_place = models.IntegerField(null=True, blank=True)
    finals_place = models.IntegerField(null=True, blank=True)
    
    # Points (calculated based on the point system)
    points = models.FloatField(default=0)
    
    # Status
    is_disqualified = models.BooleanField(default=False)
    is_exhibition = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['event', 'finals_place', 'prelim_place']
        unique_together = ['swimmer', 'event']
        
    def __str__(self):
        return f"{self.swimmer} - {self.event}"
    
    @property
    def best_time(self):
        """Return the best time (finals if available, otherwise prelims)"""
        if self.finals_time and self.finals_time > 0:
            return self.finals_time
        if self.prelim_time and self.prelim_time > 0:
            return self.prelim_time
        return self.seed_time    
        
