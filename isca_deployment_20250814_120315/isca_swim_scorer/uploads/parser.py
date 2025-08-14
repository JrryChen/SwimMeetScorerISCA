import sys
import os
import logging
import zipfile
import tempfile
from typing import Dict, List
from django.db import transaction
from django.utils.text import slugify

from meets.models import Meet, Event, Team, Swimmer, Result
from uploads.models import UploadedFile
from core.utils import format_swim_time, parse_swim_time
from scoring.scoring_system import ScoringSystem
from .dryland_parser import process_dryland_file, DrylandParseError

# Add custom parser path and import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "hytek-parser"))
from hytek_parser import hy3_parser
from hytek_parser.hy3.enums import Course, Stroke, Gender

logger = logging.getLogger(__name__)

def get_event_name(event, course: str) -> str:
    """Get the formatted event name for display and point table lookup"""
    # Get gender text
    gender_text = "Men's" if event.gender == Gender.MALE else \
                 "Women's" if event.gender == Gender.FEMALE else ""
    
    # Handle relay events
    if event.relay:
        if event.stroke == Stroke.MEDLEY:
            return f"{gender_text} {event.distance} Medley Relay ({course})"
        else:
            return f"{gender_text} {event.distance} Freestyle Relay ({course})"
    
    # Handle individual medley events
    if event.stroke == Stroke.MEDLEY:
        return f"{gender_text} {event.distance} Individual Medley ({course})"
    
    # For individual events, format properly
    stroke_str = {
        Stroke.FREESTYLE: "Freestyle",
        Stroke.BACKSTROKE: "Backstroke",
        Stroke.BREASTSTROKE: "Breaststroke",
        Stroke.BUTTERFLY: "Butterfly",
        Stroke.MEDLEY: "Individual Medley"
    }.get(event.stroke, "Unknown")
    return f"{gender_text} {event.distance} {stroke_str} ({course})"

def extract_hy3_from_zip(zip_path: str) -> str:
    """
    Extract HY3 file from ZIP archive.
    
    Args:
        zip_path: Path to the ZIP file
        
    Returns:
        Path to the extracted HY3 file
        
    Raises:
        ValueError: If ZIP doesn't contain exactly one HY3 file
    """
    hy3_files = []
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        # Find all HY3 files in the ZIP
        for file in zip_ref.namelist():
            if file.lower().endswith('.hy3'):
                hy3_files.append(file)
        
        if not hy3_files:
            raise ValueError("No HY3 files found in the ZIP archive")
        if len(hy3_files) > 1:
            raise ValueError("ZIP archive contains multiple HY3 files. Please include only one HY3 file.")
            
        # Extract the HY3 file to a temporary directory
        temp_dir = tempfile.mkdtemp()
        zip_ref.extract(hy3_files[0], temp_dir)
        
        return os.path.join(temp_dir, hy3_files[0])

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
        
        # Check if file is a ZIP and extract if needed
        if file_path.lower().endswith('.zip'):
            logger.info("Detected ZIP file, extracting HY3 file...")
            file_path = extract_hy3_from_zip(file_path)
            logger.info(f"Extracted HY3 file to: {file_path}")
        
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
            
            # Skip relay events completely
            if event.relay:
                logger.info(f"Skipping relay event: {event.number}")
                continue
                
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
                    gender=event.gender.value,
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
                
                # Calculate points using best_time
                point_age = None  # Don't use age for points in relay events
                if not event.relay:
                    point_age = entry.swimmers[0].age if entry.swimmers[0].age and entry.swimmers[0].age > 0 else None
                
                # Determine best time
                best_time = None
                if entry.finals_time and entry.finals_time > 0:
                    best_time = entry.finals_time
                elif entry.prelim_time and entry.prelim_time > 0:
                    best_time = entry.prelim_time
                elif entry.swimoff_time and entry.swimoff_time > 0:
                    best_time = entry.swimoff_time
                
                # Calculate points
                points = None
                if best_time:
                    points = round(scoring.calculate_points(event_name, best_time, point_age, event.age_max, gender), 2)
                
                result_entry = {
                    "swimmer": swimmer_name,
                    "raw_age": point_age,
                    "prelim_time": prelim_time,
                    "swimoff_time": swimoff_time,
                    "final_time": final_time,
                    "points": points,
                    "gender": gender,
                    "team_code": entry.swimmers[0].team_code,
                    "team_name": parsed_file.meet.teams.get(entry.swimmers[0].team_code, Team(name="Unknown Team")).name,
                    "swimmer_meet_id": str(entry.swimmers[0].meet_id),
                    "usa_swimming_id": entry.swimmers[0].usa_swimming_id
                }
                event_results.append(result_entry)

                # Save to database if meet is provided
                if meet and event_obj:
                    # Get or create the team
                    team, _ = Team.objects.get_or_create(
                        meet=meet,
                        code=entry.swimmers[0].team_code,
                        defaults={
                            'name': parsed_file.meet.teams.get(entry.swimmers[0].team_code, "Unknown Team").name,
                            'short_name': entry.swimmers[0].team_code
                        }
                    )

                    if event.relay:
                        # For relay events, create a special swimmer entry with team name
                        swimmer_obj, _ = Swimmer.objects.get_or_create(
                            meet=meet,
                            team=team,
                            swimmer_meet_id=f"RELAY_{entry.swimmers[0].team_code}_{event.number}",
                            defaults={
                                'first_name': team.name,
                                'last_name': f"Relay {event.number}",
                                'gender': gender,
                                'age': None  # No age for relay teams
                            }
                        )
                    else:
                        # For individual events, create normal swimmer entry
                        swimmer_obj, _ = Swimmer.objects.get_or_create(
                            meet=meet,
                            team=team,
                            swimmer_meet_id=entry.swimmers[0].meet_id,
                            defaults={
                                'first_name': entry.swimmers[0].first_name,
                                'last_name': entry.swimmers[0].last_name,
                                'gender': gender,
                                'age': entry.swimmers[0].age if entry.swimmers[0].age and entry.swimmers[0].age > 0 else None
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
                        result.prelim_points = scoring.calculate_points(event_name, result.prelim_time, point_age, event.age_max, gender)
                    if result.swim_off_time:
                        result.swim_off_points = scoring.calculate_points(event_name, result.swim_off_time, point_age, event.age_max, gender)
                    if result.final_time:
                        result.final_points = scoring.calculate_points(event_name, result.final_time, point_age, event.age_max, gender)

                    result.best_points = max(result.prelim_points, result.swim_off_points, result.final_points)
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

def determine_file_type(file_path: str) -> str:
    """
    Determine the type of file to process based on file extension
    
    Args:
        file_path: Path to the file
        
    Returns:
        File type string ('hytek', 'dryland', or 'unknown')
    """
    _, ext = os.path.splitext(file_path.lower())
    
    if ext in ['.hy3']:
        return 'hytek'
    elif ext in ['.zip']:
        # Could be either - we'll need to check contents
        return 'zip'
    elif ext in ['.xlsx', '.xls']:
        return 'dryland'
    else:
        return 'unknown'

@transaction.atomic
def process_uploaded_file(file_path: str, file_type: str, meet: Meet = None) -> Dict[str, List[dict]]:
    """
    Main file processing router that handles different file types
    
    Args:
        file_path: Path to the file to process
        file_type: Type of file (from UploadedFile.file_type)
        meet: Optional Meet instance to associate results with
        
    Returns:
        Dictionary of event results
    """
    try:
        logger.info(f"Processing file: {file_path} (type: {file_type})")
        
        if file_type in ['HY3', 'ZIP']:
            # Process as Hytek file
            return process_hytek_file(file_path, meet)
        elif file_type == 'XLSX':
            # Process as dryland file
            return process_dryland_file(file_path, meet)
        else:
            # Auto-detect based on file extension
            detected_type = determine_file_type(file_path)
            
            if detected_type == 'hytek':
                return process_hytek_file(file_path, meet)
            elif detected_type == 'dryland':
                return process_dryland_file(file_path, meet)
            elif detected_type == 'zip':
                # Try as Hytek first, then dryland
                try:
                    return process_hytek_file(file_path, meet)
                except Exception:
                    return process_dryland_file(file_path, meet)
            else:
                raise ValueError(f"Unsupported file type: {file_type}")
                
    except DrylandParseError as e:
        logger.error(f"Dryland parsing error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}", exc_info=True)
        raise
