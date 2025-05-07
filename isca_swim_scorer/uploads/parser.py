import sys
import logging
from typing import Dict, List
from django.db import transaction
from django.utils.text import slugify

from meets.models import Meet, Event, Team, Swimmer, Result
from uploads.models import UploadedFile

# Add custom parser path and import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "hytek-parser"))
from hytek_parser import hy3_parser
from hytek_parser.hy3.enums import Course, Stroke, Gender

logger = logging.getLogger(__name__)

def get_event_name(event) -> str:
    """Convert event details into a readable name."""
    gender_str = {
        Gender.MALE: "Men's",
        Gender.FEMALE: "Women's",
        Gender.UNKNOWN: "Mixed"
    }.get(event.gender, "Unknown")

    stroke_str = {
        Stroke.FREESTYLE: "Freestyle",
        Stroke.BACKSTROKE: "Backstroke",
        Stroke.BREASTSTROKE: "Breaststroke",
        Stroke.BUTTERFLY: "Butterfly",
        Stroke.MEDLEY: "Medley"
    }.get(event.stroke, "Unknown")

    return f"{gender_str} {event.distance} {stroke_str} ({event.course.name})"

def process_hytek_file(file_path: str) -> Dict[str, List[dict]]:
    """
    Process a Hytek file and return organized results.
    
    Args:
        file_path: Path to the Hytek file to process
        
    Returns:
        Dictionary of event results with swimmer times
    """
    try:
        logger.info(f"Starting to process Hytek file: {file_path}")
        
        # Parse the file
        parsed_file = hy3_parser.parse_hy3(file_path)
        events = parsed_file.meet.events
        event_ids = list(events.keys())
        
        # Extract and organize event results
        results = {}

        for event_id in event_ids:
            event = events[event_id]
            event_name = get_event_name(event)
            event_results = []

            for entry in event.entries:
                swimmer = entry.swimmers[0]
                swimmer_name = f"{swimmer.first_name} {swimmer.middle_initial + ' ' if swimmer.middle_initial else ''}{swimmer.last_name}"
                
                result_entry = {
                    "swimmer": swimmer_name,
                    "age": swimmer.age,
                    "prelim_time": entry.prelim_time,
                    "swimoff_time": entry.swimoff_time,
                    "final_time": entry.finals_time
                }
                event_results.append(result_entry)

            # Sort by final time, ignoring missing or zero times
            event_results.sort(
                key=lambda x: float('inf') if not x['final_time'] or x['final_time'] == 0.0 else x['final_time']
            )
            results[event_name] = event_results
            
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

