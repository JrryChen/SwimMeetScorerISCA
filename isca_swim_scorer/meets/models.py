from django.db import models
from django.utils.text import slugify
from core.models import Course, Stroke, Gender, TimeStampedModel

# Create your models here.

class Meet(TimeStampedModel):
    """
    Represents a swim meet
    """

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    location = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    course = models.CharField(max_length=255, choices=Course.choices, default=Course.SHORT_COURSE_YARDS)

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
    Represents a Swim Team at a Meet
    """
    
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=255)
    short_name = models.CharField(max_length=50, blank=True)
    meet = models.ForeignKey(Meet, on_delete=models.CASCADE, related_name='teams')

    class Meta:
        ordering = ['name']
        unique_together = ['code', 'meet']

    def __str__(self):
        return self.name
    
class Swimmer(TimeStampedModel):
    """
    Represents a Swimmer
    """

    first_name = models.CharField(max_length=255)
    middle_name = models.CharField(max_length=255, blank=True)
    last_name = models.CharField(max_length=255)
    gender = models.CharField(max_length=1, choices=Gender.choices)
    date_of_birth = models.DateField(null=True, blank=True)
    age = models.IntegerField(null=True, blank=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='swimmers')
    meet = models.ForeignKey(Meet, on_delete=models.CASCADE, related_name='swimmers')

    # hytek specific ids
    swimmer_meet_id = models.CharField(max_length=20, blank=True)
    usa_swimming_id = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ['last_name', 'first_name']
        unique_together = ['swimmer_meet_id', 'meet']
    
    def __str__(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def full_name(self):
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        else:
            return f"{self.first_name} {self.last_name}"
    
class Event(TimeStampedModel):
    """
    Represents a swim event
    """

    meet = models.ForeignKey(Meet, on_delete=models.CASCADE, related_name='events')
    event_number = models.IntegerField()
    name = models.CharField(max_length=255)
    distance = models.IntegerField()
    stroke = models.CharField(max_length=255, choices=Stroke.choices)
    gender = models.CharField(max_length=1, choices=Gender.choices)
    is_relay = models.BooleanField(default=False)
    min_age = models.IntegerField(null=True, blank=True)
    max_age = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['event_number']
        unique_together = ['meet', 'event_number']

    def __str__(self):
        return f"{self.event_number} - {self.name}"
    
    @property
    def event_key(self):
        """Generate a unique key for lookup in point systems"""
        gender_text = "Men's" if self.gender == Gender.MALE else \
                    "Women's" if self.gender == Gender.FEMALE else "Mixed"
        
        # Handle relay events
        if self.is_relay:
            if self.stroke == Stroke.MEDLEY_RELAY:
                return f"{gender_text} {self.distance} Medley Relay ({self.meet.course})"
            else:
                return f"{gender_text} {self.distance} Freestyle Relay ({self.meet.course})"
        
        # Handle individual events
        stroke_display = self.get_stroke_display() # displays the name of stroke
        return f"{gender_text} {self.distance} {stroke_display} ({self.meet.course})"
    
class Result(TimeStampedModel):
    """
    Represents a swimmer's time result in an event and converted points
    """

    swimmer = models.ForeignKey(Swimmer, on_delete=models.CASCADE, related_name='results')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='results')

    # Time in seconds
    seed_time = models.FloatField(null=True, blank=True)
    prelim_time = models.FloatField(null=True, blank=True)
    swim_off_time = models.FloatField(null=True, blank=True)
    final_time = models.FloatField(null=True, blank=True)

    # Places
    prelim_place = models.IntegerField(null=True, blank=True)
    swim_off_place = models.IntegerField(null=True, blank=True)
    final_place = models.IntegerField(null=True, blank=True)

    prelim_points = models.FloatField(default=0)
    swim_off_points = models.FloatField(default=0)
    final_points = models.FloatField(default=0)

    # Status
    is_disqualified = models.BooleanField(default=False)
    is_exhibition = models.BooleanField(default=False)

    class Meta:
        ordering = ['event', 'final_place', 'prelim_place', 'swim_off_place']

    def __str__(self):
        return f"{self.swimmer} - {self.event} - {self.final_time}"
    
    @property
    def best_time(self):
        """Return the best time from the final, prelim, or swim_off time; return 0 if none exist"""
        times = []
        if self.final_time and self.final_time > 0:
            times.append(self.final_time)
        if self.prelim_time and self.prelim_time > 0:
            times.append(self.prelim_time)
        if self.swim_off_time and self.swim_off_time > 0:
            times.append(self.swim_off_time)
        
        return min(times) if times else 0