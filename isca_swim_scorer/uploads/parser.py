import sys
import os
import logging
from typing import Dict, List
from django.db import transaction
from django.utils.text import slugify

from meets.models import Meet, Event, Team, Swimmer, Result
from uploads.models import UploadedFile
from core.utils import format_swim_time, parse_swim_time
from scoring.scoring_system import ScoringSystem

# Add custom parser path and import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "hytek-parser"))
from hytek_parser import hy3_parser
from hytek_parser.hy3.enums import Course, Stroke, Gender

logger = logging.getLogger(__name__)

def get_event_name(event, course: str) -> str:
    """Get the formatted event name for display and point table lookup"""
    # Handle relay events
    if event.relay:
        if event.stroke == Stroke.MEDLEY:
            return f"{event.distance} Medley Relay ({course})"
        else:
            return f"{event.distance} Freestyle Relay ({course})"
    
    # Handle individual medley events
    if event.stroke == Stroke.MEDLEY:
        return f"{event.distance} Individual Medley ({course})"
    
    # For individual events, format properly
    stroke_str = {
        Stroke.FREESTYLE: "Freestyle",
        Stroke.BACKSTROKE: "Backstroke",
        Stroke.BREASTSTROKE: "Breaststroke",
        Stroke.BUTTERFLY: "Butterfly",
        Stroke.MEDLEY: "Individual Medley"
    }.get(event.stroke, "Unknown")
    
    return f"{event.distance} {stroke_str} ({course})"

@transaction.atomic
def process_hytek_file(file_path: str, meet: Meet = None) -> Dict[str, List[dict]]:
    """
    Process a Hytek file and return organized results.
    
    Args:
        file_path: Path to the Hytek file to process
        meet: Optional Meet instance to associate results with
        
    Returns:
        Dictionary of event results with swimmer times
    """
    try:
        logger.info(f"Starting to process Hytek file: {file_path}")
        
        # Parse the file
        parsed_file = hy3_parser.parse_hy3(file_path)
        events = parsed_file.meet.events
        event_ids = list(events.keys())
        
        # Get the meet's course
        meet_course = parsed_file.meet.course
        
        # Extract and organize event results
        results = {}
        scoring = ScoringSystem()

        for event_id in event_ids:
            event = events[event_id]
            event_name = get_event_name(event, meet_course.name)
            event_results = []

            # Create the event in database if meet is provided
            event_obj = None
            if meet:
                event_obj = Event.objects.create(
                    meet=meet,
                    event_number=event.number,
                    name=event_name,
                    distance=event.distance,
                    stroke=event.stroke.name,
                    gender=event.gender.name,
                    is_relay=event.relay,
                    min_age=event.age_min,
                    max_age=event.age_max
                )

            for entry in event.entries:
                swimmer = entry.swimmers[0]
                swimmer_name = f"{swimmer.first_name} {swimmer.middle_initial + ' ' if swimmer.middle_initial else ''}{swimmer.last_name}"
                
                # Convert gender to string
                gender = swimmer.gender
                if isinstance(gender, Gender):
                    gender = gender.name
                
                # Format times for display - times are already in seconds
                prelim_time = format_swim_time(entry.prelim_time) if entry.prelim_time and entry.prelim_time > 0 else "-"
                swimoff_time = format_swim_time(entry.swimoff_time) if entry.swimoff_time and entry.swimoff_time > 0 else "-"
                final_time = format_swim_time(entry.finals_time) if entry.finals_time and entry.finals_time > 0 else "-"
                
                # Format age for display - show N/A if age is 0 or None
                display_age = "N/A" if not swimmer.age or swimmer.age == 0 else swimmer.age
                
                # Calculate points using best_time
                point_age = swimmer.age if swimmer.age and swimmer.age > 0 else None
                
                # Determine best time
                best_time = None
                if entry.finals_time and entry.finals_time > 0:
                    best_time = entry.finals_time
                elif entry.swimoff_time and entry.swimoff_time > 0:
                    best_time = entry.swimoff_time
                elif entry.prelim_time and entry.prelim_time > 0:
                    best_time = entry.prelim_time

                # Calculate points
                points = None
                if best_time:
                    points = round(scoring.calculate_points(event_name, best_time, point_age, event.age_max, swimmer.gender), 2)
                
                result_entry = {
                    "swimmer": swimmer_name,
                    "age": display_age,
                    "raw_age": swimmer.age,
                    "prelim_time": prelim_time,
                    "swimoff_time": swimoff_time,
                    "final_time": final_time,
                    "points": points,
                    "gender": gender,
                    "team_code": swimmer.team_code,
                    "team_name": parsed_file.meet.teams.get(swimmer.team_code, Team(name="Unknown Team")).name,
                    "swimmer_meet_id": str(swimmer.meet_id),
                    "usa_swimming_id": swimmer.usa_swimming_id
                }
                event_results.append(result_entry)

                # Save to database if meet is provided
                if meet and event_obj:
                    # Get or create the team
                    team, _ = Team.objects.get_or_create(
                        meet=meet,
                        code=swimmer.team_code,
                        defaults={
                            'name': parsed_file.meet.teams.get(swimmer.team_code, "Unknown Team").name,
                            'short_name': swimmer.team_code
                        }
                    )

                    # Get or create the swimmer
                    swimmer_obj, _ = Swimmer.objects.get_or_create(
                        meet=meet,
                        team=team,
                        swimmer_meet_id=swimmer.meet_id,
                        defaults={
                            'first_name': swimmer.first_name,
                            'last_name': swimmer.last_name,
                            'gender': event.gender.name,
                            'age': swimmer.age if swimmer.age and swimmer.age > 0 else None
                        }
                    )

                    # Create the result
                    result = Result.objects.create(
                        event=event_obj,
                        swimmer=swimmer_obj,
                        prelim_time=entry.prelim_time,
                        swim_off_time=entry.swimoff_time,
                        final_time=entry.finals_time
                    )

                    # Calculate points for each time
                    if result.prelim_time:
                        result.prelim_points = scoring.calculate_points(event_name, result.prelim_time, swimmer.age, event.age_max, swimmer.gender)
                        logger.info(f"Prelim points for {swimmer_obj.full_name} in {event_name}: {result.prelim_points}")
                    if result.swim_off_time:
                        result.swim_off_points = scoring.calculate_points(event_name, result.swim_off_time, swimmer.age, event.age_max, swimmer.gender)
                        logger.info(f"Swim-off points for {swimmer_obj.full_name} in {event_name}: {result.swim_off_points}")
                    if result.final_time:
                        result.final_points = scoring.calculate_points(event_name, result.final_time, swimmer.age, event.age_max, swimmer.gender)
                        logger.info(f"Final points for {swimmer_obj.full_name} in {event_name}: {result.final_points}")

                    result.best_points = max(result.prelim_points, result.swim_off_points, result.final_points)
                    logger.info(f"Best points for {swimmer_obj.full_name} in {event_name}: {result.best_points}")
                    result.save()

            # Sort by final time, ignoring missing or zero times
            event_results.sort(
                key=lambda x: float('inf') if x['final_time'] == '-' else parse_swim_time(x['final_time'])
            )
                
            results[event_name] = event_results
            
        logger.info(f"Successfully processed {len(results)} events")
        return results
        
    except Exception as e:
        logger.error(f"Error processing Hytek file: {str(e)}", exc_info=True)
        raise
