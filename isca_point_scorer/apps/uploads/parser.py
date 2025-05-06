import os
import logging
from typing import Tuple, Optional

from django.conf import settings
from django.db import transaction
from django.utils.text import slugify

from isca_point_scorer.apps.meets.models import Meet, Team, Swimmer, Event, Result
from isca_point_scorer.apps.uploads.models import UploadedFile

logger = logging.getLogger(__name__)

def parse_hy3_file(uploaded_file: UploadedFile) -> Tuple[bool, Optional[Meet], str]:
    """
    Parse a HY3 file and create records in our database.
    
    Args:
        uploaded_file: The UploadedFile instance containing the HY3 file
        
    Returns:
        Tuple of (success, meet, message)
    """
    try:
        # Import dynamically to avoid dependency issues
        import sys
        sys.path.insert(0, "/hytek-parser")  # path to your forked parser folder
        from hytek_parser import hy3_parser
        
        # Get the file path
        file_path = uploaded_file.file.path
        
        # Parse the file
        parsed_file = hy3_parser.parse_hy3(file_path)
        
        # Process the parsed data
        with transaction.atomic():
            # Create or get the meet
            meet_name = parsed_file.meet.name
            if not meet_name:
                meet_name = os.path.splitext(uploaded_file.original_filename)[0]
                
            meet, created = Meet.objects.update_or_create(
                name=meet_name,
                defaults={
                    'slug': slugify(meet_name),
                    'location': getattr(parsed_file.meet, 'facility', ''),
                    'start_date': parsed_file.meet.start_date,
                    'end_date': parsed_file.meet.end_date,
                    'course': _map_course(parsed_file.meet.course),
                }
            )
            
            # Update the uploaded file reference
            uploaded_file.meet = meet
            uploaded_file.save()
            
            # Process teams
            for team_code, team_data in parsed_file.meet.teams.items():
                team, _ = Team.objects.update_or_create(
                    code=team_code,
                    meet=meet,
                    defaults={
                        'name': team_data.name,
                        'short_name': team_data.short_name or team_data.code,
                    }
                )
            
            # Process swimmers
            for swimmer_id, swimmer_data in parsed_file.meet.swimmers.items():
                # Find the team for this swimmer
                team = Team.objects.filter(code=swimmer_data.team_code, meet=meet).first()
                if not team:
                    # Create a default team if needed
                    team, _ = Team.objects.get_or_create(
                        code=swimmer_data.team_code or 'UNA',
                        meet=meet,
                        defaults={
                            'name': 'Unattached',
                            'short_name': 'UNA',
                        }
                    )
                
                swimmer, _ = Swimmer.objects.update_or_create(
                    meet_id=str(swimmer_id),
                    meet=meet,
                    defaults={
                        'first_name': swimmer_data.first_name,
                        'last_name': swimmer_data.last_name,
                        'gender': _map_gender(swimmer_data.gender),
                        'date_of_birth': swimmer_data.date_of_birth,
                        'age': swimmer_data.age,
                        'team': team,
                        'usa_swimming_id': getattr(swimmer_data, 'usa_swimming_id', ''),
                    }
                )
            
            # Process events
            for event_number, event_data in parsed_file.meet.events.items():
                event, _ = Event.objects.update_or_create(
                    event_number=event_number,
                    meet=meet,
                    defaults={
                        'name': _build_event_name(event_data),
                        'distance': event_data.distance,
                        'stroke': _map_stroke(event_data.stroke),
                        'gender': _map_gender(event_data.gender),
                        'is_relay': event_data.relay,
                        'min_age': event_data.age_min,
                        'max_age': event_data.age_max,
                    }
                )
                
                # Process results for this event
                for entry in event_data.entries:
                    # Skip relay entries for now (unless you want to implement relay handling)
                    if event_data.relay:
                        continue
                    
                    if not entry.swimmers or len(entry.swimmers) == 0:
                        continue
                    
                    # Get the swimmer
                    swimmer_id = entry.swimmers[0].meet_id
                    try:
                        swimmer = Swimmer.objects.get(meet_id=str(swimmer_id), meet=meet)
                    except Swimmer.DoesNotExist:
                        logger.warning(f"Swimmer {swimmer_id} not found for event {event_number}")
                        continue
                    
                    # Extract times
                    seed_time = _convert_hytek_time_to_seconds(entry.seed_time)
                    prelim_time = _convert_hytek_time_to_seconds(entry.prelim_time)
                    finals_time = _convert_hytek_time_to_seconds(entry.finals_time)
                    
                    # Check for DQ
                    is_disqualified = bool(entry.prelim_dq_info or entry.finals_dq_info)
                    
                    # Create the result
                    result, _ = Result.objects.update_or_create(
                        swimmer=swimmer,
                        event=event,
                        defaults={
                            'seed_time': seed_time,
                            'prelim_time': prelim_time,
                            'finals_time': finals_time,
                            'prelim_place': entry.prelim_overall_place,
                            'finals_place': entry.finals_overall_place,
                            'is_disqualified': is_disqualified,
                        }
                    )
            
            # Mark the file as processed
            uploaded_file.is_processed = True
            uploaded_file.save()
            
            return True, meet, f"Successfully imported meet: {meet.name}"
            
    except Exception as e:
        logger.exception(f"Error parsing HY3 file: {str(e)}")
        error_message = f"Error parsing file: {str(e)}"
        uploaded_file.processing_errors = error_message
        uploaded_file.save()
        return False, None, error_message

def _map_course(hytek_course):
    """Map Hytek course enum to our Course choices"""
    course_mapping = {
        'Y': 'SCY',  # Short Course Yards
        'S': 'SCM',  # Short Course Meters
        'L': 'LCM',  # Long Course Meters
    }
    return course_mapping.get(str(hytek_course), 'SCY')

def _map_gender(hytek_gender):
    """Map Hytek gender enum to our Gender choices"""
    gender_mapping = {
        'M': 'M',  # Male
        'F': 'F',  # Female
        'X': 'X',  # Mixed
    }
    return gender_mapping.get(str(hytek_gender), 'U')

def _map_stroke(hytek_stroke):
    """Map Hytek stroke enum to our Stroke choices"""
    stroke_mapping = {
        'A': 'FR',  # Freestyle
        'B': 'BK',  # Backstroke
        'C': 'BR',  # Breaststroke
        'D': 'FL',  # Butterfly
        'E': 'IM',  # Individual Medley
    }
    return stroke_mapping.get(str(hytek_stroke), 'FR')

def _build_event_name(event_data):
    """Build a descriptive name for the event"""
    gender = "Men's" if str(event_data.gender) == 'M' else "Women's" if str(event_data.gender) == 'F' else "Mixed"
    relay = "Relay " if event_data.relay else ""
    stroke = {
        'A': 'Freestyle',
        'B': 'Backstroke',
        'C': 'Breaststroke',
        'D': 'Butterfly',
        'E': 'Individual Medley',
    }.get(str(event_data.stroke), 'Unknown')
    
    age_group = ""
    if event_data.age_min > 0 or event_data.age_max < 109:
        if event_data.age_min == 0:
            age_group = f"{event_data.age_max} & Under "
        elif event_data.age_max >= 109:
            age_group = f"{event_data.age_min} & Over "
        else:
            age_group = f"{event_data.age_min}-{event_data.age_max} "
    
    return f"{gender} {age_group}{relay}{event_data.distance} {stroke}"

def _convert_hytek_time_to_seconds(hytek_time):
    """Convert a Hytek time to seconds"""
    if hytek_time is None:
        return None
        
    # If it's already a float, it's in seconds
    if isinstance(hytek_time, (int, float)):
        return float(hytek_time) if hytek_time > 0 else None
        
    # Otherwise, it might be a string or time code
    return None