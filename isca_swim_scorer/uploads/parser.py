import sys
import os
import logging
from typing import Dict, List
from django.db import transaction
from django.utils.text import slugify

from meets.models import Meet, Event, Team, Swimmer, Result
from uploads.models import UploadedFile
from core.utils import format_swim_time, parse_swim_time

# Add custom parser path and import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "hytek-parser"))
from hytek_parser import hy3_parser
from hytek_parser.hy3.enums import Course, Stroke, Gender

logger = logging.getLogger(__name__)

def get_event_name(event, meet_course: Course) -> str:
    """Convert event details into a readable name."""
    gender_str = {
        Gender.MALE: "Men's",
        Gender.FEMALE: "Women's",
        Gender.UNKNOWN: "Mixed"
    }.get(event.gender, "Unknown")

    # Handle relay events
    if event.relay:
        if event.stroke == Stroke.MEDLEY:
            return f"{gender_str} {event.distance} Medley Relay ({meet_course.name})"
        else:
            return f"{gender_str} {event.distance} Freestyle Relay ({meet_course.name})"
    
    # Handle individual events
    stroke_str = {
        Stroke.FREESTYLE: "Freestyle",
        Stroke.BACKSTROKE: "Backstroke",
        Stroke.BREASTSTROKE: "Breaststroke",
        Stroke.BUTTERFLY: "Butterfly",
        Stroke.MEDLEY: "Individual Medley"
    }.get(event.stroke, "Unknown")

    return f"{gender_str} {event.distance} {stroke_str} ({meet_course.name})"

@transaction.atomic
def save_event_to_db(meet: Meet, event, event_name: str, results: List[dict], entries):
    """Save an event and its results to the database."""
    # Create or get the event
    event_obj, created = Event.objects.get_or_create(
        meet=meet,
        event_number=int(event.number),
        defaults={
            'name': event_name,
            'distance': event.distance,
            'stroke': event.stroke.name,
            'gender': event.gender.name,
            'is_relay': event.relay,
            'min_age': event.age_min,
            'max_age': event.age_max
        }
    )

    # Save results
    for result, entry in zip(results, entries):
        # Create or get the swimmer
        swimmer_name = result['swimmer']
        first_name, *middle, last_name = swimmer_name.split()
        middle_name = ' '.join(middle) if middle else ''
        
        # Get or create the team first
        team_code = result.get('team_code', 'UNKNOWN')
        team_name = result.get('team_name', 'Unknown Team')
        team, _ = Team.objects.get_or_create(
            meet=meet,
            code=team_code,
            defaults={
                'name': team_name,
                'short_name': team_code
            }
        )
        
        # Convert gender to string if it's an enum
        gender = result.get('gender', Gender.UNKNOWN)
        if isinstance(gender, Gender):
            gender = gender.name
        
        # Now create the swimmer with both team and meet
        swimmer, created = Swimmer.objects.get_or_create(
            first_name=first_name,
            last_name=last_name,
            meet=meet,
            defaults={
                'middle_name': middle_name,
                'team': team,
                'gender': gender,
                'age': result['raw_age'],  # Use raw age for database
                'swimmer_meet_id': result.get('swimmer_meet_id', ''),
                'usa_swimming_id': result.get('usa_swimming_id', '')
            }
        )

        # Create the result using raw times from the entry
        Result.objects.create(
            event=event_obj,
            swimmer=swimmer,
            prelim_time=entry.prelim_time,
            swim_off_time=entry.swimoff_time,
            final_time=entry.finals_time
        )

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

        for event_id in event_ids:
            event = events[event_id]
            event_name = get_event_name(event, meet_course)
            event_results = []
            event_entries = []

            for entry in event.entries:
                swimmer = entry.swimmers[0]
                swimmer_name = f"{swimmer.first_name} {swimmer.middle_initial + ' ' if swimmer.middle_initial else ''}{swimmer.last_name}"
                
                # Convert gender to string
                gender = swimmer.gender
                if isinstance(gender, Gender):
                    gender = gender.name
                
                # Format times for display
                prelim_time = format_swim_time(entry.prelim_time) if entry.prelim_time else None
                swimoff_time = format_swim_time(entry.swimoff_time) if entry.swimoff_time else None
                final_time = format_swim_time(entry.finals_time) if entry.finals_time else None
                
                # Format age for display - show N/A if age is 0
                display_age = "N/A" if swimmer.age == 0 else swimmer.age
                
                result_entry = {
                    "swimmer": swimmer_name,
                    "age": display_age,  # Formatted age for display
                    "raw_age": swimmer.age,  # Raw age for database
                    "prelim_time": prelim_time,
                    "swimoff_time": swimoff_time,
                    "final_time": final_time,
                    "gender": gender,
                    "team_code": swimmer.team_code,
                    "team_name": parsed_file.meet.teams.get(swimmer.team_code, Team(name="Unknown Team")).name,
                    "swimmer_meet_id": str(swimmer.meet_id),
                    "usa_swimming_id": swimmer.usa_swimming_id
                }
                event_results.append(result_entry)
                event_entries.append(entry)

            # Sort by final time, ignoring missing or zero times
            sorted_pairs = sorted(
                zip(event_results, event_entries),
                key=lambda x: float('inf') if not x[1].finals_time or x[1].finals_time == 0.0 else x[1].finals_time
            )
            event_results, event_entries = zip(*sorted_pairs)
            event_results = list(event_results)
            event_entries = list(event_entries)
                
            results[event_name] = event_results
            
            # Save to database if meet is provided
            if meet:
                save_event_to_db(meet, event, event_name, event_results, event_entries)
            
        logger.info(f"Successfully processed {len(results)} events")
        return results
        
    except Exception as e:
        logger.error(f"Error processing Hytek file: {str(e)}", exc_info=True)
        raise

# Example usage
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Example file path
    sample_file = "../../SampleMeetResults/Meet Results-PCS Spring Home Meet 2025-22Mar2025-002.hy3"
    
    # Process the file
    results = process_hytek_file(sample_file)
    
    # Print results for each event
    for event_name, event_results in results.items():
        print(f"\n{event_name}:")
        for result in event_results:
            print(f"Swimmer: {result['swimmer']}")
            print(f"  Age: {result['age']}")
            print(f"  Prelim Time: {result['prelim_time']}")
            print(f"  Swimoff Time: {result['swimoff_time']}")
            print(f"  Final Time: {result['final_time']}")
            print("---")

