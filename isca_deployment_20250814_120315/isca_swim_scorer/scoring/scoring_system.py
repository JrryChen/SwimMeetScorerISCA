from typing import Dict, Union, Optional
import numpy as np
from scipy.interpolate import interp1d
from .pointSystem import pointSystem6, pointSystem7, pointSystem8, pointSystem9, pointSystem10, pointSystem11, pointSystem12, pointSystem13, pointSystem14, pointSystem15plus
from core.utils import parse_swim_time
from core.models import Gender

class ScoringSystem:
    def __init__(self):
        """Initialize the scoring system with all point system versions."""
        self.point_systems = {
            6: pointSystem6,
            7: pointSystem7,
            8: pointSystem8,
            9: pointSystem9,
            10: pointSystem10,
            11: pointSystem11,
            12: pointSystem12,
            13: pointSystem13,
            14: pointSystem14,
            15: pointSystem15plus,  # For 15 and older
        }

    def _get_point_table(self, event_key: str, age: Optional[int] = None, event_max_age: Optional[int] = None) -> Optional[Dict[float, float]]:
        """Get the appropriate point table for an event and age."""
        words = event_key.split(" ")
        event_gender = words[0]
        actual_event = " ".join(words[1:])

        if event_gender == "Mixed":
            event_gender = "Men's"

        # If age is None, use event max age if available, otherwise use 15plus
        if age is None:
            if event_max_age is not None:
                point_age = event_max_age
            else:
                point_age = 15  # Use 15plus scoring system as fallback
        else:
            point_age = age if age > 0 and age < 15 else 15
            
        # Get the appropriate point system for the age
        point_system = self.point_systems.get(point_age)
        if not point_system:
            # If no exact match, use the 15plus system
            point_system = self.point_systems.get(15)
            if not point_system:
                print(f"Warning: No point system found for age {point_age}")
                return None
        
        # Get the point table for the event
        return point_system.get(event_gender).get(actual_event)

    def calculate_points(self, event_key: str, time: float, age: Optional[int] = None, event_max_age: Optional[int] = None, gender: Optional[str] = None) -> float:
        """Calculate points for a given event and time"""
        # Get the appropriate point table based on age
        point_table = self._get_point_table(event_key, age, event_max_age)
        
        # If no point table found, return 0 points
        if point_table is None:
            # print(f"Warning: No point table found for event {event_key} with age {age}, event max age {event_max_age}, and gender {gender}")
            return 0.0
        # else:
        #     print(f"Point table found for event {event_key} with age {age}, event max age {event_max_age}, and gender {gender}")
            
        
        # Convert time to seconds if it's a string
        if isinstance(time, str):
            time = parse_swim_time(time)
            
        # If time is None or 0, return 0 points
        if time is None or time <= 0:
            return 0.0
            
        # Get the point values and times from the table
        time_points = sorted(point_table.items())
        points = [s for _, s in time_points]
        times = [t for t, _ in time_points]

        f = interp1d(times, points, bounds_error=False, fill_value="extrapolate")
        score = float(f(time))
        return score if score > 0 else 0.0


    def calculate_result_points(self, result) -> None:
        """
        Calculate and update points for a Result object.
        
        Args:
            result: A Result model instance
        """
        event_key = result.event.event_key
        
        # Calculate points for each time type if it exists
        if result.prelim_time and result.prelim_time > 0:
            result.prelim_points = self.calculate_points(event_key, result.prelim_time, result.swimmer.age, result.event.max_age)
            
        if result.swim_off_time and result.swim_off_time > 0:
            result.swim_off_points = self.calculate_points(event_key, result.swim_off_time, result.swimmer.age, result.event.max_age)
            
        if result.final_time and result.final_time > 0:
            result.final_points = self.calculate_points(event_key, result.final_time, result.swimmer.age, result.event.max_age)
            
        result.save()

    def calculate_meet_points(self, meet) -> None:
        """
        Calculate points for all results in a meet.
        
        Args:
            meet: A Meet model instance
        """
        for result in meet.results.all():
            self.calculate_result_points(result) 