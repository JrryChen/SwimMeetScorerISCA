import sys
import os
import logging
from typing import Dict, List, Tuple, Optional
from django.db import transaction
from django.utils.text import slugify

from meets.models import Meet, Event, Team, Swimmer, Result
from uploads.models import UploadedFile
from scoring.scoring_system import ScoringSystem
from core.models import Stroke, Gender

logger = logging.getLogger(__name__)

# Add hytek-parser path for xlrd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "hytek-parser"))

try:
    import xlrd
    XLRD_AVAILABLE = True
except ImportError:
    XLRD_AVAILABLE = False

try:
    from openpyxl import load_workbook
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

class DrylandParseError(Exception):
    """Exception raised when parsing dryland Excel files fails"""
    pass

def detect_excel_format(file_path: str) -> str:
    """Detect if the Excel file is XLS or XLSX format"""
    _, ext = os.path.splitext(file_path.lower())
    return ext

def parse_excel_data(file_path: str) -> Tuple[List[str], List[List]]:
    """
    Parse Excel file and return headers and data rows
    
    Returns:
        Tuple of (headers, data_rows)
    """
    file_format = detect_excel_format(file_path)
    
    if file_format == '.xlsx' and OPENPYXL_AVAILABLE:
        return parse_xlsx_with_openpyxl(file_path)
    elif file_format == '.xls' and XLRD_AVAILABLE:
        return parse_xls_with_xlrd(file_path)
    else:
        raise DrylandParseError(f"Unsupported file format {file_format} or missing required library")

def parse_xlsx_with_openpyxl(file_path: str) -> Tuple[List[str], List[List]]:
    """Parse XLSX file using openpyxl"""
    try:
        workbook = load_workbook(file_path, read_only=True)
        worksheet = workbook.active
        
        # Get all rows as values
        rows = list(worksheet.values)
        
        if not rows:
            raise DrylandParseError("Excel file is empty")
        
        # Find header row (look for a row containing 'Name' or 'Athlete')
        header_row_idx = 0
        headers = None
        
        for i, row in enumerate(rows[:10]):  # Check first 10 rows
            if row and any(cell and str(cell).lower().strip() in ['name', 'athlete', 'swimmer'] for cell in row):
                header_row_idx = i
                headers = [str(cell).strip() if cell else '' for cell in row]
                break
        
        if headers is None:
            # If no clear header found, assume first row
            headers = [str(cell).strip() if cell else '' for cell in rows[0]]
            header_row_idx = 0
        
        # Get data rows
        data_rows = []
        for row in rows[header_row_idx + 1:]:
            if row and any(cell for cell in row):  # Skip empty rows
                data_rows.append([str(cell).strip() if cell else '' for cell in row])
        
        return headers, data_rows
        
    except Exception as e:
        raise DrylandParseError(f"Error parsing XLSX file: {str(e)}")

def parse_xls_with_xlrd(file_path: str) -> Tuple[List[str], List[List]]:
    """Parse XLS file using xlrd"""
    try:
        workbook = xlrd.open_workbook(file_path)
        worksheet = workbook.sheet_by_index(0)
        
        if worksheet.nrows == 0:
            raise DrylandParseError("Excel file is empty")
        
        # Find header row
        header_row_idx = 0
        headers = None
        
        for i in range(min(10, worksheet.nrows)):  # Check first 10 rows
            row = [str(worksheet.cell_value(i, j)).strip() for j in range(worksheet.ncols)]
            if any(cell.lower() in ['name', 'athlete', 'swimmer'] for cell in row if cell):
                header_row_idx = i
                headers = row
                break
        
        if headers is None:
            # If no clear header found, assume first row
            headers = [str(worksheet.cell_value(0, j)).strip() for j in range(worksheet.ncols)]
            header_row_idx = 0
        
        # Get data rows
        data_rows = []
        for i in range(header_row_idx + 1, worksheet.nrows):
            row = [str(worksheet.cell_value(i, j)).strip() for j in range(worksheet.ncols)]
            if any(cell for cell in row):  # Skip empty rows
                data_rows.append(row)
        
        return headers, data_rows
        
    except Exception as e:
        raise DrylandParseError(f"Error parsing XLS file: {str(e)}")

def identify_columns(headers: List[str]) -> Dict[str, int]:
    """
    Identify column indices for important fields
    
    Returns:
        Dictionary mapping field names to column indices
    """
    column_mapping = {}
    
    for i, header in enumerate(headers):
        header_lower = header.lower().strip()
        
        # First Name column
        if header_lower in ['first name', 'firstname', 'first', 'fname']:
            column_mapping['first_name'] = i
        
        # Last Name column
        elif header_lower in ['last name', 'lastname', 'last', 'lname', 'surname']:
            column_mapping['last_name'] = i
        
        # Full Name column (fallback if first/last not separate)
        elif header_lower in ['name', 'athlete', 'swimmer', 'athlete name', 'swimmer name', 'full name']:
            if 'first_name' not in column_mapping and 'last_name' not in column_mapping:
                column_mapping['name'] = i
        
        # Age column
        elif header_lower in ['age', 'athlete age', 'swimmer age']:
            column_mapping['age'] = i
        
        # Team column
        elif header_lower in ['team', 'club', 'team name', 'club name', 'team code']:
            column_mapping['team'] = i
        
        # Gender column
        elif 'gender' in header_lower or header_lower in ['sex', 'm/f', 'male/female']:
            column_mapping['gender'] = i
        
        # Event score columns - specific dryland events
        elif (header and 
              any(event in header_lower for event in [
                  'chin-up', 'chinup', 'chin up', 'pull-up', 'pullup', 'pull up',
                  'dip', 'dips', 'tricep dip', 'tricep dips',
                  'vertical jump', 'vert jump', 'jump', 'standing jump',
                  'push-up', 'pushup', 'push up', 'press-up', 'pressup',
                  'sit-up', 'situp', 'sit up', 'crunch', 'crunches',
                  'plank', 'planks', 'plank hold',
                  'burpee', 'burpees',
                  'sprint', 'run', 'dash', 'mile', '100m', '200m', '400m',
                  'squat', 'squats', 'leg press',
                  'bench', 'bench press',
                  'deadlift', 'dead lift'
              ]) or 
              # Also catch any numeric or general event-like headers
              (header_lower.replace(' ', '').replace('-', '').replace('(', '').replace(')', '').isalnum() and 
               len(header_lower) > 2 and 
               not header_lower in ['age', 'team', 'name', 'first', 'last', 'gender'])):
            if 'events' not in column_mapping:
                column_mapping['events'] = []
            column_mapping['events'].append({'name': header, 'index': i})
    
    return column_mapping

def parse_athlete_name(name_str: str) -> Tuple[str, str]:
    """
    Parse athlete name into first and last name
    
    Args:
        name_str: Full name string
        
    Returns:
        Tuple of (first_name, last_name)
    """
    if not name_str:
        return "", ""
    
    parts = name_str.strip().split()
    if len(parts) == 1:
        return parts[0], ""
    elif len(parts) == 2:
        return parts[0], parts[1]
    else:
        # More than 2 parts - first is first name, rest is last name
        return parts[0], " ".join(parts[1:])

def safe_int(value: str, default: Optional[int] = None) -> Optional[int]:
    """Safely convert string to integer"""
    try:
        return int(float(value)) if value and value.strip() else default
    except (ValueError, TypeError):
        return default

def safe_float(value: str, default: Optional[float] = None) -> Optional[float]:
    """Safely convert string to float"""
    try:
        return float(value) if value and value.strip() else default
    except (ValueError, TypeError):
        return default

def parse_gender(gender_str: str) -> str:
    """
    Parse gender string into Django model format
    
    Args:
        gender_str: Gender string from Excel (M, F, Other, etc.)
        
    Returns:
        Gender code for Django model
    """
    if not gender_str:
        return Gender.UNKNOWN
    
    gender_lower = str(gender_str).lower().strip()
    
    if gender_lower in ['m', 'male', 'man', 'boy']:
        return Gender.MALE
    elif gender_lower in ['f', 'female', 'woman', 'girl']:
        return Gender.FEMALE
    elif gender_lower in ['x', 'mixed', 'other', 'non-binary', 'nb']:
        return Gender.MIXED
    else:
        return Gender.UNKNOWN

def normalize_event_name_for_scoring(event_name: str) -> str:
    """
    Normalize event name to match the point system naming convention.
    
    Point system has: "Chin-Ups", "Dips", "Vertical Jump"
    Excel might have: "Chin-ups", "Dips", "Vertical Jump (In)", etc.
    """
    event_name = event_name.strip()
    
    # Handle common variations
    if "chin" in event_name.lower() and "up" in event_name.lower():
        return "Chin-Ups"
    elif "dip" in event_name.lower():
        return "Dips"
    elif "vertical" in event_name.lower() and "jump" in event_name.lower():
        return "Vertical Jump"
    
    # If no match found, return the original name
    return event_name

def get_age_group(age: int) -> tuple[int, int]:
    """
    Get the age group min and max ages for a given age.
    
    Age groups: 6, 7, 8, 9, 10, 11, 12, 13, 14, 15+
    
    Args:
        age: The swimmer's age
        
    Returns:
        Tuple of (min_age, max_age) for the age group
    """
    if age < 6:
        return (6, 6)  # Default to 6 if age is too young
    elif age >= 15:
        return (15, 99)  # 15+ age group
    else:
        return (age, age)  # Individual age groups for 6-14

@transaction.atomic
def process_dryland_file(file_path: str, meet: Meet = None) -> Dict[str, List[dict]]:
    """
    Process a dryland Excel file and return organized results.
    
    Args:
        file_path: Path to the Excel file to process
        meet: Optional Meet instance to associate results with
        
    Returns:
        Dictionary of event results with athlete scores
    """
    try:
        logger.info(f"Starting to process dryland file: {file_path}")
        
        # Parse the Excel file
        headers, data_rows = parse_excel_data(file_path)
        
        if not data_rows:
            raise DrylandParseError("No data rows found in Excel file")
        
        # Identify column structure
        column_mapping = identify_columns(headers)
        
        if ('name' not in column_mapping and 
            ('first_name' not in column_mapping or 'last_name' not in column_mapping)):
            raise DrylandParseError("Could not find athlete name columns (need either 'name' or both 'first_name' and 'last_name')")
        
        if 'events' not in column_mapping:
            raise DrylandParseError("Could not find any event score columns")
        
        # Initialize scoring system
        scoring = ScoringSystem()
        
        # Process data and organize by events
        results = {}
        
        # Create events for each score column and age group
        for event_info in column_mapping['events']:
            # Clean up event name for better display
            clean_event_name = event_info['name'].strip()
            # Remove parenthetical units for the display name but keep the info
            if '(' in clean_event_name and ')' in clean_event_name:
                base_name = clean_event_name.split('(')[0].strip()
                unit = clean_event_name.split('(')[1].split(')')[0].strip()
                base_event_name = f"Dryland - {base_name}"
                if unit:
                    base_event_name += f" ({unit})"
            else:
                base_event_name = f"Dryland - {clean_event_name}"
            
            # Create events for each age group and gender
            age_groups = [(6, 6), (7, 7), (8, 8), (9, 9), (10, 10), (11, 11), (12, 12), (13, 13), (14, 14), (15, 99)]
            genders = [Gender.MALE, Gender.FEMALE]
            
            for gender in genders:
                for min_age, max_age in age_groups:
                    # Get gender prefix
                    gender_prefix = "Men's" if gender == Gender.MALE else "Women's"
                    
                    # Get age group display name
                    if max_age == 99:
                        age_display = "Open"
                    else:
                        age_display = str(min_age)
                    
                    # Create event name with gender and age group
                    event_name = f"{gender_prefix} {base_event_name.replace('Dryland - ', '')} - {age_display}"
                    results[event_name] = []
        
        # Process each athlete row
        for row_idx, row in enumerate(data_rows):
            try:
                # Extract athlete info
                if 'first_name' in column_mapping and 'last_name' in column_mapping:
                    # Prefer separate first/last name columns
                    first_name = row[column_mapping['first_name']] if column_mapping['first_name'] < len(row) else ""
                    last_name = row[column_mapping['last_name']] if column_mapping['last_name'] < len(row) else ""
                    full_name = f"{first_name} {last_name}".strip()
                elif 'name' in column_mapping:
                    # Fall back to full name column
                    full_name = row[column_mapping['name']] if column_mapping['name'] < len(row) else ""
                    first_name, last_name = parse_athlete_name(full_name)
                else:
                    continue  # Skip if no name info
                
                if not full_name or not first_name:
                    continue  # Skip empty name rows
                
                # Extract age
                age = None
                if 'age' in column_mapping and column_mapping['age'] < len(row):
                    age = safe_int(row[column_mapping['age']])
                
                # Extract team
                team_name = ""
                if 'team' in column_mapping and column_mapping['team'] < len(row):
                    team_name = row[column_mapping['team']]
                
                # Extract gender
                gender = Gender.UNKNOWN
                if 'gender' in column_mapping and column_mapping['gender'] < len(row):
                    gender = parse_gender(row[column_mapping['gender']])
                
                # Process each event score
                for event_info in column_mapping['events']:
                    # Use the same event name generation logic
                    clean_event_name = event_info['name'].strip()
                    if '(' in clean_event_name and ')' in clean_event_name:
                        base_name = clean_event_name.split('(')[0].strip()
                        unit = clean_event_name.split('(')[1].split(')')[0].strip()
                        base_event_name = f"Dryland - {base_name}"
                        if unit:
                            base_event_name += f" ({unit})"
                    else:
                        base_event_name = f"Dryland - {clean_event_name}"
                    score_col = event_info['index']
                    
                    if score_col < len(row):
                        score = safe_float(row[score_col])
                        
                        if score is not None and score > 0:
                            # Calculate points using the scoring system
                            scoring_system = ScoringSystem()
                            
                            # Normalize event name for scoring system
                            normalized_event_name = normalize_event_name_for_scoring(clean_event_name)
                            
                            # Map gender to point system format
                            gender_for_scoring = "Men's" if gender == Gender.MALE else "Women's" if gender == Gender.FEMALE else "Men's"  # Default to Men's if unknown
                            
                            # Create event key for scoring (e.g., "Men's Chin-Ups" or "Women's Dips")
                            event_key = f"{gender_for_scoring} {normalized_event_name}"
                            
                            # Calculate points based on the scoring system
                            points = scoring_system.calculate_points(event_key, score, age)
                            
                            # If no points found in scoring system, fall back to raw score
                            if points == 0:
                                points = score
                            
                            # Determine age group for this result
                            min_age, max_age = get_age_group(age or 12)  # Default to age 12 if no age provided
                            
                            # Get gender prefix for event name
                            gender_prefix = "Men's" if gender == Gender.MALE else "Women's"
                            
                            # Get age group display name
                            if max_age == 99:
                                age_display = "Open"
                            else:
                                age_display = str(min_age)
                            
                            # Create the age group event name for database with gender
                            age_group_event_name = f"{gender_prefix} {base_event_name.replace('Dryland - ', '')} - {age_display}"
                            
                            result_entry = {
                                "swimmer": full_name,
                                "raw_age": age,
                                "score": score,
                                "points": points,
                                "gender": gender,
                                "team_code": team_name[:10] if team_name else "UNKNOWN",
                                "team_name": team_name or "Unknown Team",
                                "event_type": "dryland",
                                "min_age": min_age,
                                "max_age": max_age
                            }
                            
                            # Add to results using age group event name
                            results[age_group_event_name].append(result_entry)
                            
                            # Save to database if meet is provided
                            if meet:
                                # Get or create the team
                                team, _ = Team.objects.get_or_create(
                                    meet=meet,
                                    code=result_entry["team_code"],
                                    defaults={
                                        'name': result_entry["team_name"],
                                        'short_name': result_entry["team_code"]
                                    }
                                )
                                
                                # Create swimmer
                                swimmer_obj, _ = Swimmer.objects.get_or_create(
                                    meet=meet,
                                    team=team,
                                    swimmer_meet_id=f"DRYLAND_{slugify(full_name)}_{row_idx}",
                                    defaults={
                                        'first_name': first_name,
                                        'last_name': last_name,
                                        'gender': gender,
                                        'age': age
                                    }
                                )
                                
                                # Get or create event with age group
                                event_obj, _ = Event.objects.get_or_create(
                                    meet=meet,
                                    name=age_group_event_name,
                                    defaults={
                                        'event_number': 9000 + event_info['index'] + (min_age * 100),  # High numbers for dryland events with age group offset
                                        'distance': 0,  # No distance for dryland
                                        'stroke': Stroke.OTHER,
                                        'gender': Gender.UNKNOWN,  # Mixed/Unknown
                                        'is_relay': False,
                                        'min_age': min_age,
                                        'max_age': max_age
                                    }
                                )
                                
                                # Create result
                                result = Result.objects.create(
                                    event=event_obj,
                                    swimmer=swimmer_obj,
                                    final_time=score,  # Store score as "time"
                                    final_points=points,
                                    best_points=points
                                )
                                
            except Exception as e:
                logger.warning(f"Error processing row {row_idx}: {str(e)}")
                continue
        
        # Sort each event's results by score (descending for dryland - higher is better)
        for event_name in results:
            results[event_name].sort(key=lambda x: x['score'], reverse=True)
        
        logger.info(f"Successfully processed {len(results)} dryland events")
        return results
        
    except Exception as e:
        logger.error(f"Error processing dryland file: {str(e)}", exc_info=True)
        raise 