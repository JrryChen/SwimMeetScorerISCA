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
    if minutes > 0:
        return f"{int(minutes)}:{seconds:05.2f}"
    else:
        return f"{seconds:.2f}"

def parse_swim_time(time_str):
    """
    Parse a swim time string to seconds.
    
    Examples:
    - "23.45" -> 23.45
    - "1:03.21" -> 63.21
    """
    if not time_str or time_str == "---":
        return 0
    
    parts = time_str.split(':')
    if len(parts) == 1:
        return float(parts[0])
    else:
        minutes = float(parts[0])
        seconds = float(parts[1])
        return minutes * 60 + seconds