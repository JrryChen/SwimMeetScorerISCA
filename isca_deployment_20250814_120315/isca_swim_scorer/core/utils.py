import logging

logger = logging.getLogger(__name__)

def format_swim_time(seconds):
    """
    Format a swim time in seconds to a human-readable format.
    
    Example:
    - 23.45 -> "23.45"
    - 63.21 -> "1:03.21"
    - 123.45 -> "2:03.45"
    """
    if not seconds or seconds <= 0:
        return "---"
    
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{int(hours)}:{int(minutes)}:{seconds:05.2f}"
    elif minutes > 0:
        return f"{int(minutes)}:{seconds:05.2f}"
    else:
        return f"{seconds:.2f}"

def format_dryland_score(score):
    """
    Format a dryland score to a human-readable format.
    
    Example:
    - 23.45 -> "23.45"
    - 100 -> "100"
    - 0 -> "---"
    """
    if not score or score <= 0:
        return "---"
    
    # For whole numbers, display as integer
    if score == int(score):
        return str(int(score))
    else:
        return f"{score:.2f}"
    
def parse_swim_time(time_str):
    """
    Parse a swim time string into seconds.
    
    Example:
    - "23.45" -> 23.45
    - "1:03.21" -> 63.21
    - "2:03.45" -> 123.45   
    """
    if not time_str or time_str == "---":
        return 0
    
    parts = time_str.split(":")
    if len(parts) == 3: # hours:minutes:seconds
        hours, minutes, seconds = map(float, parts)
        return hours * 3600 + minutes * 60 + seconds
    elif len(parts) == 2: # minutes:seconds
        minutes, seconds = map(float, parts)
        return minutes * 60 + seconds
    else:
        return float(parts[0])

    



        
