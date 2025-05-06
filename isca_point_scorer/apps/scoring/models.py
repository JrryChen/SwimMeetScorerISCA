import json
from django.db import models
from django.core.exceptions import ValidationError
from scipy.interpolate import interp1d

from isca_point_scorer.apps.core.models import TimeStampedModel
from isca_point_scorer.apps.meets.models import Meet

def validate_point_system(value):
    """Validate that the JSON structure is correct for a point system"""
    try:
        data = json.loads(value)
        
        # Check basic structure (gender -> event -> time -> points)
        if not isinstance(data, dict):
            raise ValidationError("Point system must be a JSON object")
        
        for gender, events in data.items():
            if not isinstance(events, dict):
                raise ValidationError(f"Events for {gender} must be a JSON object")
            
            for event, times in events.items():
                if not isinstance(times, dict):
                    raise ValidationError(f"Times for {event} must be a JSON object")
                
                for time_str, points in times.items():
                    try:
                        float(time_str)
                    except ValueError:
                        raise ValidationError(f"Time '{time_str}' is not a valid number")
                    
                    try:
                        float(points)
                    except ValueError:
                        raise ValidationError(f"Points '{points}' is not a valid number")
                        
    except json.JSONDecodeError:
        raise ValidationError("Invalid JSON format")

class PointSystem(TimeStampedModel):
    """
    Represents a scoring system for swim meets.
    """
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    # JSON data representing the point system
    # Structure: {gender: {event: {time: points}}}
    # Example: {"Men's": {"100 Freestyle (SCY)": {"41.23": 1000, "43.56": 950}}}
    data = models.JSONField(validators=[validate_point_system])
    
    class Meta:
        ordering = ['name']
        
    def __str__(self):
        return self.name
    
    def get_points(self, gender, event_key, time_seconds):
        """
        Get points for a given time using interpolation.
        
        Args:
            gender (str): "Men's" or "Women's"
            event_key (str): Event key like "100 Freestyle (SCY)"
            time_seconds (float): Time in seconds
            
        Returns:
            float: Points for the given time
        """
        if not time_seconds or time_seconds <= 0:
            return 0
            
        data = self.data.get(gender, {})
        event_data = data.get(event_key, {})
        
        if not event_data:
            return 0
            
        # Convert dictionary to sorted list of (time, points) tuples
        time_points = [(float(t), float(p)) for t, p in event_data.items()]
        time_points.sort()
        
        times = [t for t, _ in time_points]
        points = [p for _, p in time_points]
        
        # Handle times faster than the fastest time
        if time_seconds <= times[0]:
            return points[0]
            
        # Handle times slower than the slowest time
        if time_seconds >= times[-1]:
            return max(0, points[-1] - (time_seconds - times[-1]) * 10)  # Penalty of 10 points per second
            
        # Use scipy for interpolation
        f = interp1d(times, points)
        return float(f(time_seconds))

class MeetScoring(TimeStampedModel):
    """
    Links a meet to a specific point system and stores scoring settings.
    """
    meet = models.OneToOneField(Meet, on_delete=models.CASCADE, related_name='scoring')
    point_system = models.ForeignKey(PointSystem, on_delete=models.PROTECT, related_name='meets')
    
    # Scoring settings
    include_exhibition_swims = models.BooleanField(default=False)
    include_relay_events = models.BooleanField(default=True)
    
    # Limits
    max_individual_events = models.PositiveSmallInt